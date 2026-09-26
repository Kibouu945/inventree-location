from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate

from django.db import connection
from django.test.utils import CaptureQueriesContext

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from inventree_location import roles
from inventree_location.models import (
    Lieu,
    Prestation,
    RentableItem,
    Reservation,
)
from inventree_location.views import DeliveryListView, DeliveryMarquerLivreeView
from inventree_location.tests.factories import (
    make_contact,
    make_manifestation,
)

from part.models import Part, PartCategory

User = get_user_model()


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def gestionnaire(db):
    group, _created = Group.objects.get_or_create(name=roles.GESTIONNAIRE)
    account = User.objects.create_user(username="gest", password="pwd12345")
    account.groups.add(group)
    return account


@pytest.fixture
def livreur(db):
    group, _created = Group.objects.get_or_create(name=roles.LIVREUR)
    account = User.objects.create_user(username="livreur1", password="pwd12345")
    account.groups.add(group)
    return account


@pytest.fixture
def contact(db):
    """Le contact référent : c'est lui que le bon de livraison imprime."""

    return make_contact(nom="Nisatrice", prenom="Ora", telephone="0102030405")


@pytest.fixture
def lieu(db):
    return Lieu.objects.create(
        nom="Chalet", adresse="1 rue du Camp", latitude="45.1", longitude="5.7"
    )


@pytest.fixture
def part(db):
    category = PartCategory.objects.create(name="Catégorie")
    return Part.objects.create(name="Tente", category=category)


@pytest.fixture
def manifestation(db, contact):
    return make_manifestation(
        nom="Camp",
        date_debut="2026-06-01T00:00:00Z",
        date_fin="2026-06-05T00:00:00Z",
        statut="planifiee",
        client=contact.client,
        contact=contact,
    )


@pytest.fixture
def prestation(db, manifestation, lieu):
    return Prestation.objects.create(
        manifestation=manifestation,
        nom="Prestation",
        lieu=lieu,
        date_debut="2026-06-01T00:00:00Z",
        date_fin="2026-06-05T00:00:00Z",
    )


def _make_reservation(
    prestation, part, *, statut, date_retrait, date_retour, quantite=1
):
    reservation = Reservation.objects.create(
        prestation=prestation,
        demandeur=User.objects.create_user(
            username=f"demandeur-{Reservation.objects.count()}", password="pwd"
        ),
        statut=statut,
        date_retrait_prevue=date_retrait,
        date_retour_prevue=date_retour,
    )
    reservation.lignes.create(part=part, quantite_demandee=quantite)
    return reservation


class TestDeliveryListView:
    def test_anonymous_returns_401(self, factory, prestation, part):
        _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )

        request = factory.get("/plugin/inventree-location/deliveries/")
        response = DeliveryListView.as_view()(request)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_pure_livreur_only_sees_validee_regardless_of_statut_param(
        self, factory, livreur, prestation, part
    ):
        to_deliver = _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )
        _make_reservation(
            prestation,
            part,
            statut="livree",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )

        # Un livreur pur reste forcé sur "validee" même s'il demande "livree".
        request = factory.get(
            "/plugin/inventree-location/deliveries/", {"statut": "livree"}
        )
        force_authenticate(request, user=livreur)
        response = DeliveryListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        ids = [row["id"] for row in response.data["results"]]
        assert ids == [to_deliver.pk]

    @pytest.mark.django_db
    def test_default_statut_scope_is_validee_and_livree(
        self, factory, gestionnaire, prestation, part
    ):
        validee = _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )
        livree = _make_reservation(
            prestation,
            part,
            statut="livree",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )
        _make_reservation(
            prestation,
            part,
            statut="refusee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )

        request = factory.get("/plugin/inventree-location/deliveries/")
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        ids = {row["id"] for row in response.data["results"]}
        assert ids == {validee.pk, livree.pk}

    @pytest.mark.django_db
    def test_date_filter(self, factory, gestionnaire, prestation, part):
        in_range = _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )
        _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-07-10T00:00:00Z",
            date_retour="2026-07-11T00:00:00Z",
        )

        request = factory.get(
            "/plugin/inventree-location/deliveries/",
            {"date_from": "2026-06-01", "date_to": "2026-06-30"},
        )
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        ids = [row["id"] for row in response.data["results"]]
        assert ids == [in_range.pk]

    @pytest.mark.django_db
    def test_date_to_couvre_la_journee_entiere(
        self, factory, gestionnaire, prestation, part
    ):
        """Filtrer sur « le 2 juin » doit montrer la tournée de ce jour-là."""

        du_jour = _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T08:30:00Z",
            date_retour="2026-06-06T00:00:00Z",
        )

        request = factory.get(
            "/plugin/inventree-location/deliveries/",
            {"date_from": "2026-06-02", "date_to": "2026-06-02"},
        )
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        assert [row["id"] for row in response.data["results"]] == [du_jour.pk]

    @pytest.mark.django_db
    def test_borne_horodatee_reste_exacte(
        self, factory, gestionnaire, prestation, part
    ):
        """Une borne complète garde sa précision à l'heure près."""

        _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T08:30:00Z",
            date_retour="2026-06-06T00:00:00Z",
        )

        request = factory.get(
            "/plugin/inventree-location/deliveries/",
            {"date_to": "2026-06-02T08:00:00Z"},
        )
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        assert response.data["results"] == []

    @pytest.mark.django_db
    def test_lieu_filter(self, factory, gestionnaire, manifestation, part, lieu):
        other_lieu = Lieu.objects.create(nom="Gymnase", adresse="2 rue du Sport")
        other_prestation = Prestation.objects.create(
            manifestation=manifestation,
            nom="Autre prestation",
            lieu=other_lieu,
            date_debut="2026-06-01T00:00:00Z",
            date_fin="2026-06-05T00:00:00Z",
        )
        prestation_at_lieu = Prestation.objects.create(
            manifestation=manifestation,
            nom="Prestation",
            lieu=lieu,
            date_debut="2026-06-01T00:00:00Z",
            date_fin="2026-06-05T00:00:00Z",
        )

        wanted = _make_reservation(
            prestation_at_lieu,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )
        _make_reservation(
            other_prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )

        request = factory.get(
            "/plugin/inventree-location/deliveries/", {"lieu": str(lieu.pk)}
        )
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        ids = [row["id"] for row in response.data["results"]]
        assert ids == [wanted.pk]

    @pytest.mark.django_db
    def test_le_contact_referent_alimente_les_cles_organisateur(
        self, factory, gestionnaire, prestation, part
    ):
        """Les clés `organisateur_*` sont conservées, leur source change : le"""

        reservation = _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )

        request = factory.get("/plugin/inventree-location/deliveries/")
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        row = next(r for r in response.data["results"] if r["id"] == reservation.pk)
        assert row["organisateur_telephone"] == "0102030405"
        assert "Nisatrice" in row["organisateur_nom"]

    @pytest.mark.django_db
    def test_sans_contact_on_retombe_sur_le_client(
        self, factory, gestionnaire, prestation, part
    ):
        # `contact` est nullable : on affiche alors le client, sans lever de 500.
        prestation.manifestation.contact = None
        prestation.manifestation.save(update_fields=["contact"])

        reservation = _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )

        request = factory.get("/plugin/inventree-location/deliveries/")
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        row = next(r for r in response.data["results"] if r["id"] == reservation.pk)
        assert row["organisateur_nom"] == prestation.manifestation.client.nom
        assert row["organisateur_telephone"] == ""

    @pytest.mark.django_db
    def test_quantite_totale_sums_lignes(self, factory, gestionnaire, prestation, part):
        reservation = Reservation.objects.create(
            prestation=prestation,
            demandeur=User.objects.create_user(username="dem", password="pwd"),
            statut="validee",
            date_retrait_prevue="2026-06-02T00:00:00Z",
            date_retour_prevue="2026-06-03T00:00:00Z",
        )
        reservation.lignes.create(part=part, quantite_demandee=3)
        other_category = PartCategory.objects.create(name="Autre")
        other_part = Part.objects.create(name="Piquet", category=other_category)
        reservation.lignes.create(part=other_part, quantite_demandee=5)

        request = factory.get("/plugin/inventree-location/deliveries/")
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        row = next(r for r in response.data["results"] if r["id"] == reservation.pk)
        assert row["quantite_totale"] == 8

    @pytest.mark.django_db
    def test_quantite_totale_ignore_les_articles_virtuels(
        self, factory, gestionnaire, prestation, part
    ):
        """Un service ne se charge pas dans le camion."""

        reservation = Reservation.objects.create(
            prestation=prestation,
            demandeur=User.objects.create_user(username="dem-virt", password="pwd"),
            statut="validee",
            date_retrait_prevue="2026-06-02T00:00:00Z",
            date_retour_prevue="2026-06-03T00:00:00Z",
        )
        reservation.lignes.create(part=part, quantite_demandee=4)

        service = Part.objects.create(name="Nettoyage", category=part.category)
        RentableItem.objects.create(part=service, is_virtual=True)
        reservation.lignes.create(part=service, quantite_demandee=1)

        request = factory.get("/plugin/inventree-location/deliveries/")
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        row = next(r for r in response.data["results"] if r["id"] == reservation.pk)
        assert row["quantite_totale"] == 4

    @pytest.mark.django_db
    def test_lieu_detail_null_when_prestation_has_no_lieu(
        self, factory, gestionnaire, manifestation, part
    ):
        prestation_sans_lieu = Prestation.objects.create(
            manifestation=manifestation,
            nom="Prestation sans lieu",
            date_debut="2026-06-01T00:00:00Z",
            date_fin="2026-06-05T00:00:00Z",
        )
        reservation = _make_reservation(
            prestation_sans_lieu,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )

        request = factory.get("/plugin/inventree-location/deliveries/")
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        row = next(r for r in response.data["results"] if r["id"] == reservation.pk)
        assert row["lieu_detail"] is None


LIVRER_URL = "/plugin/inventree-location/deliveries/{pk}/livrer/"


class TestMarquerLivree:
    """Passage « validée → livrée » depuis la tournée du livreur."""

    @pytest.fixture
    def reservation_validee(self, db, prestation):
        return Reservation.objects.create(
            prestation=prestation,
            demandeur=User.objects.create_user(username="dem-livr", password="pwd"),
            statut="validee",
            date_retrait_prevue="2026-06-02T00:00:00Z",
            date_retour_prevue="2026-06-03T00:00:00Z",
        )

    def _post(self, factory, user, reservation):
        request = factory.post(LIVRER_URL.format(pk=reservation.pk), {}, format="json")
        force_authenticate(request, user=user)
        return DeliveryMarquerLivreeView.as_view()(request, pk=reservation.pk)

    @pytest.mark.django_db
    def test_le_livreur_peut_marquer_livree(
        self, factory, livreur, reservation_validee
    ):
        response = self._post(factory, livreur, reservation_validee)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["statut"] == "livree"

        reservation_validee.refresh_from_db()
        assert reservation_validee.statut == "livree"

    @pytest.mark.django_db
    def test_le_gestionnaire_aussi(self, factory, gestionnaire, reservation_validee):
        assert (
            self._post(factory, gestionnaire, reservation_validee).status_code
            == status.HTTP_200_OK
        )

    @pytest.mark.django_db
    def test_un_role_sans_droit_est_refuse(self, factory, db, reservation_validee):
        lecteur = User.objects.create_user(username="lecteur-x", password="pwd")
        lecteur.groups.add(Group.objects.get_or_create(name=roles.LECTEUR)[0])

        response = self._post(factory, lecteur, reservation_validee)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        reservation_validee.refresh_from_db()
        assert reservation_validee.statut == "validee"

    @pytest.mark.django_db
    def test_une_reservation_non_validee_renvoie_409(
        self, factory, livreur, reservation_validee
    ):
        reservation_validee.statut = "brouillon"
        reservation_validee.save()

        response = self._post(factory, livreur, reservation_validee)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["current_status"] == "brouillon"

    @pytest.mark.django_db
    def test_reservation_inconnue_renvoie_404(self, factory, livreur, db):
        request = factory.post(LIVRER_URL.format(pk=999999), {}, format="json")
        force_authenticate(request, user=livreur)

        response = DeliveryMarquerLivreeView.as_view()(request, pk=999999)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestQuantitesDeLaTournee:
    """Ce que la tournée dit d'une ligne : demandée, déposée, restante."""

    def _ligne(self, factory, user, reservation):
        request = factory.get("/plugin/inventree-location/deliveries/")
        force_authenticate(request, user=user)
        response = DeliveryListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK

        row = next(r for r in response.data["results"] if r["id"] == reservation.pk)

        return row["lignes"][0]

    @pytest.mark.django_db
    def test_avant_la_livraison_tout_reste_a_deposer(
        self, factory, gestionnaire, prestation, part
    ):
        reservation = _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
            quantite=4,
        )

        ligne = self._ligne(factory, gestionnaire, reservation)

        assert ligne["quantite_demandee"] == 4
        assert ligne["quantite_deposee"] == 0
        assert ligne["quantite_restante"] == 4

    @pytest.mark.django_db
    def test_apres_la_livraison_plus_rien_ne_reste(
        self, factory, gestionnaire, livreur, prestation, part
    ):
        reservation = _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
            quantite=4,
        )

        request = factory.post(LIVRER_URL.format(pk=reservation.pk), {}, format="json")
        force_authenticate(request, user=livreur)

        assert (
            DeliveryMarquerLivreeView.as_view()(request, pk=reservation.pk).status_code
            == status.HTTP_200_OK
        )

        ligne = self._ligne(factory, gestionnaire, reservation)

        assert ligne["quantite_deposee"] == 4
        assert ligne["quantite_restante"] == 0
        # La colonne du bon, elle, n'a toujours pas d'écrivain.
        assert ligne["quantite_livree"] == 0

    @pytest.mark.django_db
    def test_le_cout_de_la_liste_ne_depend_pas_du_nombre_de_bons(
        self, factory, gestionnaire, prestation, part
    ):
        """Deux mesures plutôt qu'un plafond : quatre bons, puis douze."""

        def mesure():
            request = factory.get("/plugin/inventree-location/deliveries/")
            force_authenticate(request, user=gestionnaire)

            with CaptureQueriesContext(connection) as requetes:
                reponse = DeliveryListView.as_view()(request)
                assert reponse.status_code == status.HTTP_200_OK

            return len(requetes)

        def creer(combien):
            for _ in range(combien):
                _make_reservation(
                    prestation,
                    part,
                    statut="validee",
                    date_retrait="2026-06-02T00:00:00Z",
                    date_retour="2026-06-03T00:00:00Z",
                    quantite=2,
                )

        creer(4)
        mesure()  # la première requête amorce les caches de l'application
        quatre_bons = mesure()

        creer(8)

        assert mesure() == quatre_bons


class TestPaginationDeLaTournee:
    """La tournée était la seule liste du plugin sans pagination.

    Elle renvoyait toutes les réservations validées ou livrées, avec sept
    jointures et trois préchargements, pour un écran qui en montre une journée :
    6,8 s à 10 000 réservations (cf. `docs/test-de-charge.md`). Le coût par bon
    était déjà borné — c'est l'objet du test voisin — mais leur *nombre* ne
    l'était pas.
    """

    @staticmethod
    def _appeler(factory, utilisateur, **params):
        request = factory.get("/plugin/inventree-location/deliveries/", params)
        force_authenticate(request, user=utilisateur)
        reponse = DeliveryListView.as_view()(request)

        assert reponse.status_code == status.HTTP_200_OK

        return reponse.data

    @pytest.mark.django_db
    def test_la_reponse_est_paginee(self, factory, gestionnaire, prestation, part):
        _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )

        page = self._appeler(factory, gestionnaire)

        assert set(page) >= {"count", "next", "previous", "results"}
        assert page["count"] == 1
        assert len(page["results"]) == 1

    @pytest.mark.django_db
    def test_la_page_borne_les_lignes_et_annonce_le_total(
        self, factory, gestionnaire, prestation, part
    ):
        """C'est `count` qui permet au client de signaler la troncature."""

        for _ in range(5):
            _make_reservation(
                prestation,
                part,
                statut="validee",
                date_retrait="2026-06-02T00:00:00Z",
                date_retour="2026-06-03T00:00:00Z",
            )

        page = self._appeler(factory, gestionnaire, page_size=2)

        assert page["count"] == 5
        assert len(page["results"]) == 2
        assert page["next"] is not None

    def test_la_taille_de_page_est_plafonnee(self, factory):
        """Sans plafond, `?page_size=100000` rétablirait le comportement d'avant.

        On interroge le paginateur plutôt que l'endpoint : prouver le plafond
        par la réponse demanderait de créer cinq cents bons pour observer qu'il
        n'en revient pas cinq cent un.
        """

        paginateur = DeliveryListView.pagination_class()

        demesure = Request(factory.get("/", {"page_size": 100000}))
        raisonnable = Request(factory.get("/", {"page_size": 25}))
        muette = Request(factory.get("/"))

        assert paginateur.get_page_size(demesure) == 500
        assert paginateur.get_page_size(raisonnable) == 25
        assert paginateur.get_page_size(muette) == 100

    @pytest.mark.django_db
    def test_l_ordre_de_tournee_survit_a_la_pagination(
        self, factory, gestionnaire, prestation, part
    ):
        """Le tri par retrait croissant est l'ordre du camion : il doit être global.

        Paginer un queryset non ordonné rendrait les pages instables ; ici
        l'ordre vient du `get_queryset`, et la première page est bien celle des
        premiers retraits.
        """

        for jour in ("05", "03", "04"):
            _make_reservation(
                prestation,
                part,
                statut="validee",
                date_retrait=f"2026-06-{jour}T08:00:00Z",
                date_retour=f"2026-06-{jour}T18:00:00Z",
            )

        page = self._appeler(factory, gestionnaire, page_size=2)
        retraits = [ligne["date_retrait_prevue"] for ligne in page["results"]]

        assert [horodatage[8:10] for horodatage in retraits] == ["03", "04"]
