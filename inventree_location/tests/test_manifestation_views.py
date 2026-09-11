"""Tests des vues Manifestation (ORG-01) : CRUD, RBAC, validation des dates."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location import roles
from inventree_location.models import (
    Client,
    Manifestation,
    Prestation,
    Reservation,
    StatutManifestation,
    StatutReservation,
)
from inventree_location.views import (
    ClientListView,
    ManifestationDetailView,
    ManifestationListCreateView,
)

User = get_user_model()

MANIF_URL = "/plugin/inventree-location/manifestations/"


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def client(db):
    return Client.objects.create(nom="Jambville", email="jam@exemple.test")


def _user(username, role):
    account = User.objects.create_user(username=username, password="pwd12345")
    account.groups.add(Group.objects.get(name=role))
    return account


@pytest.fixture
def gestionnaire(db):
    return _user("alice", roles.GESTIONNAIRE)


@pytest.fixture
def lecteur(db):
    return _user("leo", roles.LECTEUR)


def _payload(client, *, days=5):
    now = timezone.now().replace(microsecond=0)
    return {
        "nom": "Camp d'été",
        "date_debut": now.isoformat(),
        "date_fin": (now + timedelta(days=days)).isoformat(),
        "statut": "brouillon",
        "client": client.pk,
    }


class TestManifestationAuth:
    def test_anonymous_returns_401(self, factory):
        request = factory.get(MANIF_URL)
        response = ManifestationListCreateView.as_view()(request)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestManifestationCrud:
    def test_create_and_list(self, factory, gestionnaire, client):
        request = factory.post(MANIF_URL, _payload(client), format="json")
        force_authenticate(request, user=gestionnaire)
        response = ManifestationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["prestations_count"] == 0

        request = factory.get(MANIF_URL)
        force_authenticate(request, user=gestionnaire)
        response = ManifestationListCreateView.as_view()(request)
        assert len(response.data["results"]) == 1

    def test_reader_cannot_create(self, factory, lecteur, client):
        request = factory.post(MANIF_URL, _payload(client), format="json")
        force_authenticate(request, user=lecteur)
        response = ManifestationListCreateView.as_view()(request)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_invalid_dates_rejected(self, factory, gestionnaire, client):
        payload = _payload(client)
        payload["date_fin"] = payload["date_debut"]
        # fin avant début
        now = timezone.now().replace(microsecond=0)
        payload["date_debut"] = (now + timedelta(days=2)).isoformat()
        payload["date_fin"] = now.isoformat()

        request = factory.post(MANIF_URL, payload, format="json")
        force_authenticate(request, user=gestionnaire)
        response = ManifestationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "date_fin" in response.data

    def test_update_and_delete(self, factory, gestionnaire, client):
        manif = Manifestation.objects.create(
            nom="À renommer",
            date_debut=timezone.now(),
            date_fin=timezone.now() + timedelta(days=1),
            client=client,
        )

        request = factory.patch(
            f"{MANIF_URL}{manif.pk}/", {"nom": "Renommée"}, format="json"
        )
        force_authenticate(request, user=gestionnaire)
        response = ManifestationDetailView.as_view()(request, pk=manif.pk)
        assert response.status_code == status.HTTP_200_OK
        manif.refresh_from_db()
        assert manif.nom == "Renommée"

        request = factory.delete(f"{MANIF_URL}{manif.pk}/")
        force_authenticate(request, user=gestionnaire)
        response = ManifestationDetailView.as_view()(request, pk=manif.pk)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Manifestation.objects.filter(pk=manif.pk).exists()


@pytest.mark.django_db
class TestManifestationStatutWorkflow:
    def test_response_expose_statut_effectif(self, factory, gestionnaire, client):
        now = timezone.now()
        manif = Manifestation.objects.create(
            nom="En cours",
            date_debut=now - timedelta(hours=1),
            date_fin=now + timedelta(days=2),
            statut=StatutManifestation.PLANIFIEE,
            client=client,
        )
        request = factory.get(f"{MANIF_URL}{manif.pk}/")
        force_authenticate(request, user=gestionnaire)
        response = ManifestationDetailView.as_view()(request, pk=manif.pk)

        assert response.status_code == status.HTTP_200_OK
        # Statut stocké = planifiée, mais effectif = en_cours (dérivé des dates).
        assert response.data["statut"] == StatutManifestation.PLANIFIEE
        assert response.data["statut_effectif"] == StatutManifestation.EN_COURS

    @pytest.mark.parametrize("statut", ["en_cours", "terminee"])
    def test_statut_derive_non_posable_a_la_main(
        self, factory, gestionnaire, client, statut
    ):
        manif = Manifestation.objects.create(
            nom="Manif",
            date_debut=timezone.now() + timedelta(days=3),
            date_fin=timezone.now() + timedelta(days=5),
            statut=StatutManifestation.PLANIFIEE,
            client=client,
        )
        request = factory.patch(
            f"{MANIF_URL}{manif.pk}/", {"statut": statut}, format="json"
        )
        force_authenticate(request, user=gestionnaire)
        response = ManifestationDetailView.as_view()(request, pk=manif.pk)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "statut" in response.data

    def test_annulation_cascade_annule_les_reservations(
        self, factory, gestionnaire, client
    ):
        now = timezone.now()
        manif = Manifestation.objects.create(
            nom="À annuler",
            date_debut=now + timedelta(days=3),
            date_fin=now + timedelta(days=5),
            statut=StatutManifestation.PLANIFIEE,
            client=client,
        )
        presta = Prestation.objects.create(
            manifestation=manif,
            nom="Installation",
            date_debut=manif.date_debut,
            date_fin=manif.date_debut + timedelta(hours=2),
        )
        r_validee = Reservation.objects.create(
            prestation=presta,
            demandeur=gestionnaire,
            date_demande=now,
            statut=StatutReservation.VALIDEE,
        )
        r_livree = Reservation.objects.create(
            prestation=presta,
            demandeur=gestionnaire,
            date_demande=now,
            statut=StatutReservation.LIVREE,
        )

        request = factory.patch(
            f"{MANIF_URL}{manif.pk}/",
            {"statut": StatutManifestation.ANNULEE},
            format="json",
        )
        force_authenticate(request, user=gestionnaire)
        response = ManifestationDetailView.as_view()(request, pk=manif.pk)

        assert response.status_code == status.HTTP_200_OK
        r_validee.refresh_from_db()
        r_livree.refresh_from_db()
        # La validée (pré-livraison) est annulée → stock libéré + log de transition.
        assert r_validee.statut == StatutReservation.ANNULEE
        assert r_validee.status_logs.filter(
            to_status=StatutReservation.ANNULEE
        ).exists()
        # La livrée (matériel physiquement sorti) n'est pas touchée par la cascade.
        assert r_livree.statut == StatutReservation.LIVREE


@pytest.mark.django_db
class TestClientList:
    def test_list_groupes(self, factory, gestionnaire, client):
        request = factory.get("/plugin/inventree-location/groupes/")
        force_authenticate(request, user=gestionnaire)
        response = ClientListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"][0]["nom"] == "Jambville"

    def test_gestionnaire_referent_expose(self, factory, gestionnaire, client):
        client.gestionnaire = gestionnaire
        client.save(update_fields=["gestionnaire"])

        request = factory.get("/plugin/inventree-location/clients/")
        force_authenticate(request, user=gestionnaire)
        response = ClientListView.as_view()(request)

        assert response.data["results"][0]["gestionnaire"] == gestionnaire.pk
        assert response.data["results"][0]["gestionnaire_nom"] == "alice"

    def test_gestionnaire_me_ne_rend_que_ses_clients(self, factory, gestionnaire, client):
        """L'écran d'accueil du gestionnaire n'a pas à connaître son propre id."""

        client.gestionnaire = gestionnaire
        client.save(update_fields=["gestionnaire"])
        Client.objects.create(nom="Autre maison", email="autre@exemple.test")

        request = factory.get(
            "/plugin/inventree-location/clients/", {"gestionnaire": "me"}
        )
        force_authenticate(request, user=gestionnaire)
        response = ClientListView.as_view()(request)

        assert [item["nom"] for item in response.data["results"]] == ["Jambville"]

    def test_gestionnaire_par_identifiant(self, factory, gestionnaire, client):
        client.gestionnaire = gestionnaire
        client.save(update_fields=["gestionnaire"])
        Client.objects.create(nom="Autre maison", email="autre@exemple.test")

        request = factory.get(
            "/plugin/inventree-location/clients/", {"gestionnaire": gestionnaire.pk}
        )
        force_authenticate(request, user=gestionnaire)
        response = ClientListView.as_view()(request)

        assert [item["nom"] for item in response.data["results"]] == ["Jambville"]

    def test_gestionnaire_illisible_est_ignore(self, factory, gestionnaire, client):
        # Un paramètre bancal ne doit pas vider l'écran d'accueil ni rendre 400.
        request = factory.get(
            "/plugin/inventree-location/clients/", {"gestionnaire": "moi-meme"}
        )
        force_authenticate(request, user=gestionnaire)
        response = ClientListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert [item["nom"] for item in response.data["results"]] == ["Jambville"]

    def test_anonymous_returns_401(self, factory):
        request = factory.get("/plugin/inventree-location/groupes/")
        response = ClientListView.as_view()(request)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestChampsDuPlanning:
    """Les quatre informations que la maquette Planning affiche au survol.

    Elles sont calculées par la vue, pas par le sérialiseur : agréger
    manifestation par manifestation ferait une requête par barre du planning.
    Le repli du sérialiseur reste testé, parce qu'il sert au détail.
    """

    def _liste(self, factory, user):
        request = factory.get(MANIF_URL)
        force_authenticate(request, user=user)

        return ManifestationListCreateView.as_view()(request)

    def _manifestation_avec_bons(self, gestionnaire, statuts):
        """Une manifestation, un bon par statut donné, trois objets chacun."""

        from inventree_location.tests.factories import (
            make_ligne,
            make_manifestation,
            make_part,
            make_prestation,
            make_reservation,
        )

        manifestation = make_manifestation()
        prestation = make_prestation(manifestation=manifestation)
        part = make_part(rentable=True)

        for statut in statuts:
            bon = make_reservation(
                prestation=prestation, demandeur=gestionnaire, statut=statut
            )
            make_ligne(reservation=bon, part=part, quantite_demandee=3)

        return manifestation

    def test_le_client_et_le_contact_sont_nommes(
        self, factory, gestionnaire, client
    ):
        from inventree_location.models import Contact
        from inventree_location.tests.factories import make_manifestation

        contact = Contact.objects.create(
            client=client, nom="Durand", prenom="Paule", telephone="0611223344"
        )
        make_manifestation(client=client, contact=contact)

        ligne = self._liste(factory, gestionnaire).data["results"][0]

        assert ligne["client_nom"] == client.nom
        assert ligne["organisateur_nom"] == "Paule Durand"
        assert ligne["contact_telephone"] == "0611223344"

    def test_sans_contact_le_telephone_est_vide(
        self, factory, gestionnaire, client
    ):
        from inventree_location.tests.factories import make_manifestation

        make_manifestation(client=client)

        ligne = self._liste(factory, gestionnaire).data["results"][0]

        assert ligne["contact_telephone"] == ""
        # Le libellé retombe sur le client : le livreur a toujours un nom.
        assert ligne["organisateur_nom"] == client.nom

    def test_le_volume_somme_les_bons_engages(self, factory, gestionnaire):
        self._manifestation_avec_bons(
            gestionnaire,
            [
                StatutReservation.VALIDEE,
                StatutReservation.LIVREE,
                StatutReservation.ANNULEE,  # n'engage plus rien
                StatutReservation.BROUILLON,  # pas encore engagé
            ],
        )

        ligne = self._liste(factory, gestionnaire).data["results"][0]

        assert ligne["quantite_totale"] == 6
        assert ligne["etat_livraison"] == {"bons": 2, "livres": 1, "a_livrer": 1}

    def test_le_volume_n_est_pas_multiplie_par_le_nombre_de_bons(
        self, factory, gestionnaire
    ):
        """Le piège des agrégations jointes : deux `Sum` sur deux jointures
        dans la même requête se multiplient l'une l'autre."""

        self._manifestation_avec_bons(
            gestionnaire,
            [StatutReservation.VALIDEE] * 4,
        )

        ligne = self._liste(factory, gestionnaire).data["results"][0]

        # Quatre bons de trois objets : douze, pas quarante-huit.
        assert ligne["quantite_totale"] == 12
        assert ligne["etat_livraison"]["bons"] == 4

    def test_une_manifestation_sans_bon_rend_zero(
        self, factory, gestionnaire, client
    ):
        from inventree_location.tests.factories import make_manifestation

        make_manifestation(client=client)

        ligne = self._liste(factory, gestionnaire).data["results"][0]

        assert ligne["quantite_totale"] == 0
        assert ligne["etat_livraison"] == {"bons": 0, "livres": 0, "a_livrer": 0}

    def test_la_liste_ne_fait_pas_une_requete_par_manifestation(
        self, factory, gestionnaire, django_assert_max_num_queries
    ):
        """Le vrai enjeu des annotations : un planning de dix manifestations
        ne doit pas coûter dix fois le prix d'une."""

        for _ in range(10):
            self._manifestation_avec_bons(
                gestionnaire, [StatutReservation.VALIDEE, StatutReservation.LIVREE]
            )

        with django_assert_max_num_queries(6):
            reponse = self._liste(factory, gestionnaire)

        assert len(reponse.data["results"]) == 10
        assert all(row["quantite_totale"] == 6 for row in reponse.data["results"])


@pytest.mark.django_db
class TestFenetreDuPlanning:
    """`from` / `to` : ce qui **chevauche** la fenêtre, pas ce qui y tient.

    Le planning se déplace d'une semaine à l'autre et d'un mois à l'autre :
    sans le chevauchement, une manifestation d'une semaine disparaîtrait dès
    qu'on affiche son deuxième jour.
    """

    def _noms(self, factory, user, params):
        request = factory.get(MANIF_URL, params)
        force_authenticate(request, user=user)
        response = ManifestationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK

        return {row["nom"] for row in response.data["results"]}

    @pytest.fixture
    def trois_manifestations(self, db):
        from inventree_location.tests.factories import make_manifestation

        # Horodatages avec fuseau : le serveur tourne en Europe/Paris, et une
        # date naïve déclencherait un avertissement Django à chaque création.
        make_manifestation(
            nom="Avant",
            date_debut="2026-01-05T09:00:00+01:00",
            date_fin="2026-01-09T18:00:00+01:00",
        )
        make_manifestation(
            nom="À cheval",
            date_debut="2026-01-28T09:00:00+01:00",
            date_fin="2026-02-03T18:00:00+01:00",
        )
        make_manifestation(
            nom="Après",
            date_debut="2026-03-10T09:00:00+01:00",
            date_fin="2026-03-12T18:00:00+01:00",
        )

    def test_la_fenetre_retient_ce_qui_la_chevauche(
        self, factory, gestionnaire, trois_manifestations
    ):
        noms = self._noms(
            factory, gestionnaire, {"from": "2026-02-01", "to": "2026-02-28"}
        )

        assert noms == {"À cheval"}

    def test_une_borne_seule_fonctionne(
        self, factory, gestionnaire, trois_manifestations
    ):
        assert self._noms(factory, gestionnaire, {"from": "2026-03-01"}) == {"Après"}
        assert self._noms(factory, gestionnaire, {"to": "2026-01-10"}) == {"Avant"}

    def test_le_premier_et_le_dernier_jour_sont_inclus(
        self, factory, gestionnaire, trois_manifestations
    ):
        # Bornes fournies au jour : comparées à la journée entière, sinon une
        # manifestation qui commence à 9 h le dernier jour sortirait.
        noms = self._noms(
            factory, gestionnaire, {"from": "2026-02-03", "to": "2026-02-03"}
        )

        assert noms == {"À cheval"}
