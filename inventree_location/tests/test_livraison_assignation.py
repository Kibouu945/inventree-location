"""Pool commun des livraisons et progression d'état (US-18 / US-19).

Passe par le routeur d'URL réel et l'authentification par token, comme
`test_functional_api.py` : ces endpoints se jouent au multipart et au `DELETE`,
deux choses qu'un appel direct à la vue ne vérifie pas.
"""

from __future__ import annotations

import io

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from inventree_location import roles
from inventree_location.models import (
    EtatLivraison,
    Lieu,
    LivraisonStatusLog,
    Prestation,
    Reservation,
    StatutReservation,
)
from inventree_location.tests.factories import make_manifestation
from part.models import Part, PartCategory

User = get_user_model()

BASE = "/plugin/inventree-location"

pytestmark = [pytest.mark.django_db, pytest.mark.urls("tests.functional_urls")]


def client_for(role, username):
    """APIClient authentifié par token pour un utilisateur au rôle donné."""

    user = User.objects.create_user(username=username, password="pwd12345")

    if role is not None:
        user.groups.add(Group.objects.get(name=role))

    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}"
    )

    return client, user


@pytest.fixture
def livraison(db):
    """Une réservation validée, prête à être prise par un livreur."""

    organisateur = User.objects.create_user(username="org", password="pwd12345")
    manifestation = make_manifestation(
        nom="Camp",
        date_debut="2026-06-01T00:00:00Z",
        date_fin="2026-06-05T00:00:00Z",
        statut="planifiee",
    )
    lieu = Lieu.objects.create(
        nom="Chalet", adresse="1 rue du Camp", latitude="45.1", longitude="5.7"
    )
    prestation = Prestation.objects.create(
        manifestation=manifestation,
        nom="Installation",
        lieu=lieu,
        date_debut="2026-06-01T00:00:00Z",
        date_fin="2026-06-05T00:00:00Z",
    )
    category = PartCategory.objects.create(name="Catégorie")
    part = Part.objects.create(name="Tente", category=category)

    reservation = Reservation.objects.create(
        prestation=prestation,
        demandeur=organisateur,
        statut=StatutReservation.VALIDEE,
        date_retrait_prevue="2026-06-02T08:30:00Z",
        date_retour_prevue="2026-06-06T00:00:00Z",
    )
    reservation.lignes.create(part=part, quantite_demandee=2)

    return reservation


def accepter(client, reservation):
    return client.post(f"{BASE}/deliveries/{reservation.pk}/accepter/")


def relacher(client, reservation):
    return client.delete(f"{BASE}/deliveries/{reservation.pk}/accepter/")


def changer_etat(client, reservation, etat, **extra):
    return client.patch(
        f"{BASE}/deliveries/{reservation.pk}/etat/",
        {"etat": etat, **extra},
        format="multipart",
    )


class TestAccepter:
    def test_le_livreur_sattribue_une_livraison_libre(self, livraison):
        client, livreur = client_for(roles.LIVREUR, "lucie")

        response = accepter(client, livraison)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["livreur_assigne"] == livreur.pk
        assert response.data["etat_livraison"] == EtatLivraison.ASSIGNEE
        assert response.data["etat_livraison_display"] == "Assignée"
        assert response.data["livreur_assigne_nom"] == "lucie"

        livraison.refresh_from_db()
        assert livraison.livreur_assigne_id == livreur.pk
        assert livraison.date_assignation is not None

    def test_lassignation_est_journalisee(self, livraison):
        client, livreur = client_for(roles.LIVREUR, "lucie")

        accepter(client, livraison)

        log = LivraisonStatusLog.objects.get(reservation=livraison)
        assert (log.from_etat, log.to_etat) == ("", EtatLivraison.ASSIGNEE)
        assert log.changed_by_id == livreur.pk

    def test_une_livraison_deja_prise_est_refusee(self, livraison):
        premier, _ = client_for(roles.LIVREUR, "lucie")
        second, _ = client_for(roles.LIVREUR, "marc")

        accepter(premier, livraison)
        response = accepter(second, livraison)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "autre livreur" in response.data["detail"]

    def test_reprendre_sa_propre_livraison_est_refuse(self, livraison):
        client, _ = client_for(roles.LIVREUR, "lucie")

        accepter(client, livraison)
        response = accepter(client, livraison)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "déjà assignée" in response.data["detail"]

    @pytest.mark.parametrize(
        "statut", [StatutReservation.BROUILLON, StatutReservation.LIVREE]
    )
    def test_seule_une_reservation_validee_se_prend(self, livraison, statut):
        livraison.statut = statut
        livraison.save(update_fields=["statut"])
        client, _ = client_for(roles.LIVREUR, "lucie")

        response = accepter(client, livraison)

        assert response.status_code == status.HTTP_409_CONFLICT

    def test_une_livraison_inconnue_renvoie_404(self, db):
        client, _ = client_for(roles.LIVREUR, "lucie")

        assert accepter(client, type("R", (), {"pk": 9999})).status_code == (
            status.HTTP_404_NOT_FOUND
        )

    def test_un_lecteur_ne_peut_pas_prendre_de_livraison(self, livraison):
        client, _ = client_for(roles.LECTEUR, "leo")

        assert accepter(client, livraison).status_code == status.HTTP_403_FORBIDDEN

    def test_un_anonyme_est_rejete(self, livraison):
        response = APIClient().post(f"{BASE}/deliveries/{livraison.pk}/accepter/")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRelacher:
    def test_le_porteur_remet_la_livraison_dans_le_pool(self, livraison):
        client, _ = client_for(roles.LIVREUR, "lucie")
        accepter(client, livraison)

        response = relacher(client, livraison)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["livreur_assigne"] is None
        assert response.data["etat_livraison"] == ""

        livraison.refresh_from_db()
        assert livraison.livreur_assigne_id is None
        assert livraison.date_assignation is None

    def test_un_autre_livreur_ne_peut_pas_relacher(self, livraison):
        porteur, _ = client_for(roles.LIVREUR, "lucie")
        autre, _ = client_for(roles.LIVREUR, "marc")
        accepter(porteur, livraison)

        response = relacher(autre, livraison)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_le_gestionnaire_peut_depanner_une_tournee(self, livraison):
        porteur, _ = client_for(roles.LIVREUR, "lucie")
        gestionnaire, _ = client_for(roles.GESTIONNAIRE, "gina")
        accepter(porteur, livraison)

        assert relacher(gestionnaire, livraison).status_code == status.HTTP_200_OK

    def test_une_livraison_commencee_ne_se_relache_plus(self, livraison):
        client, _ = client_for(roles.LIVREUR, "lucie")
        accepter(client, livraison)
        changer_etat(client, livraison, EtatLivraison.EN_COURS)

        response = relacher(client, livraison)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "commencée" in response.data["detail"]

    def test_relacher_une_livraison_libre_est_refuse(self, livraison):
        client, _ = client_for(roles.LIVREUR, "lucie")

        assert relacher(client, livraison).status_code == status.HTTP_409_CONFLICT


class TestProgressionEtat:
    def test_le_livreur_demarre_sa_livraison(self, livraison):
        client, _ = client_for(roles.LIVREUR, "lucie")
        accepter(client, livraison)

        response = changer_etat(client, livraison, EtatLivraison.EN_COURS)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["etat_livraison"] == EtatLivraison.EN_COURS
        assert response.data["etat_livraison_display"] == "En cours de livraison"

    def test_marquer_livree_fait_suivre_le_statut_de_la_reservation(self, livraison):
        client, _ = client_for(roles.LIVREUR, "lucie")
        accepter(client, livraison)
        changer_etat(client, livraison, EtatLivraison.EN_COURS)

        response = changer_etat(client, livraison, EtatLivraison.LIVREE)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["statut"] == StatutReservation.LIVREE

        livraison.refresh_from_db()
        assert livraison.statut == StatutReservation.LIVREE
        assert livraison.etat_livraison == EtatLivraison.LIVREE

    def test_un_probleme_signale_nest_pas_une_impasse(self, livraison):
        client, _ = client_for(roles.LIVREUR, "lucie")
        accepter(client, livraison)
        changer_etat(client, livraison, EtatLivraison.EN_COURS)

        assert (
            changer_etat(client, livraison, EtatLivraison.PROBLEME).status_code
            == status.HTTP_200_OK
        )
        assert (
            changer_etat(client, livraison, EtatLivraison.EN_COURS).status_code
            == status.HTTP_200_OK
        )

    def test_on_ne_saute_pas_letape_en_cours(self, livraison):
        client, _ = client_for(roles.LIVREUR, "lucie")
        accepter(client, livraison)

        response = changer_etat(client, livraison, EtatLivraison.LIVREE)

        assert response.status_code == status.HTTP_409_CONFLICT

        livraison.refresh_from_db()
        assert livraison.statut == StatutReservation.VALIDEE

    def test_un_etat_inconnu_est_refuse(self, livraison):
        client, _ = client_for(roles.LIVREUR, "lucie")
        accepter(client, livraison)

        response = changer_etat(client, livraison, "teleportee")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_une_livraison_libre_na_pas_detat_a_changer(self, livraison):
        client, _ = client_for(roles.LIVREUR, "lucie")

        response = changer_etat(client, livraison, EtatLivraison.EN_COURS)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "Acceptez" in response.data["detail"]

    def test_un_autre_livreur_ne_fait_pas_avancer_la_tournee(self, livraison):
        porteur, _ = client_for(roles.LIVREUR, "lucie")
        autre, _ = client_for(roles.LIVREUR, "marc")
        accepter(porteur, livraison)

        response = changer_etat(autre, livraison, EtatLivraison.EN_COURS)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_commentaire_et_photo_sont_journalises(self, livraison):
        client, _ = client_for(roles.LIVREUR, "lucie")
        accepter(client, livraison)

        # Le plus petit GIF valide : Pillow doit pouvoir l'ouvrir.
        gif = io.BytesIO(
            b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
            b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
            b"\x00\x02\x02D\x01\x00;"
        )
        gif.name = "constat.gif"

        response = changer_etat(
            client,
            livraison,
            EtatLivraison.EN_COURS,
            commentaire="Portail fermé, je reviens",
            photo=gif,
        )

        assert response.status_code == status.HTTP_200_OK

        log = LivraisonStatusLog.objects.filter(
            reservation=livraison, to_etat=EtatLivraison.EN_COURS
        ).get()
        assert log.commentaire == "Portail fermé, je reviens"
        assert log.photo.name.endswith(".gif")

        entree = response.data["livraison_status_logs"][0]
        assert entree["to_etat_display"] == "En cours de livraison"
        assert entree["changed_by_nom"] == "lucie"
        assert entree["photo"] is not None


class TestSerialisation:
    def test_une_livraison_libre_expose_des_champs_vides(self, livraison):
        client, _ = client_for(roles.GESTIONNAIRE, "gina")

        response = client.get(f"{BASE}/deliveries/")
        ligne = response.data[0]

        assert ligne["livreur_assigne"] is None
        assert ligne["livreur_assigne_nom"] == ""
        assert ligne["date_assignation"] is None
        assert ligne["etat_livraison"] == ""
        assert ligne["etat_livraison_display"] == ""
        assert ligne["livraison_status_logs"] == []
