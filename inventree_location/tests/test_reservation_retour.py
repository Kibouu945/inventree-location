from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from part.models import Part
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location import roles
from inventree_location.models import (
    LigneReservation,
    Prestation,
    RentableItem,
    Reservation,
    StatutReservation,
)
from inventree_location.views import ReservationRetourView
from inventree_location.tests.factories import make_manifestation

User = get_user_model()

RETOUR_URL = "/plugin/inventree-location/reservations/{pk}/retour/"


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def magasinier(db):
    group, _created = Group.objects.get_or_create(name=roles.MAGASINIER)
    account = User.objects.create_user(username="mag", password="pwd12345")
    account.groups.add(group)
    return account


@pytest.fixture
def prestation(db, magasinier):
    now = timezone.now().replace(microsecond=0)
    manifestation = make_manifestation(
        nom="Camp été 2026",
        date_debut=now,
        date_fin=now + timedelta(days=7),
    )
    return Prestation.objects.create(
        manifestation=manifestation,
        nom="Installation",
        date_debut=now,
        date_fin=now + timedelta(hours=4),
    )


@pytest.fixture
def reservation_livree(db, prestation, magasinier):
    return Reservation.objects.create(
        prestation=prestation,
        demandeur=magasinier,
        statut=StatutReservation.LIVREE,
        date_demande=timezone.now(),
    )


@pytest.fixture
def deux_lignes(db, reservation_livree):
    tente = Part.objects.create(name="Tente 4 places")
    chaise = Part.objects.create(name="Chaise")
    ligne_tente = LigneReservation.objects.create(
        reservation=reservation_livree,
        part=tente,
        quantite_demandee=5,
    )
    ligne_chaise = LigneReservation.objects.create(
        reservation=reservation_livree,
        part=chaise,
        quantite_demandee=10,
    )
    return ligne_tente, ligne_chaise


class TestRetourEndpointGet:
    @pytest.mark.django_db
    def test_get_renvoie_les_lignes_si_livree(
        self, factory, magasinier, reservation_livree, deux_lignes
    ):
        request = factory.get(RETOUR_URL.format(pk=reservation_livree.pk))
        force_authenticate(request, user=magasinier)

        response = ReservationRetourView.as_view()(request, pk=reservation_livree.pk)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["statut_retour"] == "aucun"
        assert response.data["quantite_demandee_totale"] == 15
        assert len(response.data["lignes"]) == 2

    @pytest.mark.django_db
    def test_get_refuse_si_statut_incompatible(self, factory, magasinier, prestation):
        reservation = Reservation.objects.create(
            prestation=prestation,
            demandeur=magasinier,
            statut=StatutReservation.SOUMISE,
            date_demande=timezone.now(),
        )
        request = factory.get(RETOUR_URL.format(pk=reservation.pk))
        force_authenticate(request, user=magasinier)

        response = ReservationRetourView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.django_db
    def test_get_reservation_introuvable_renvoie_404(self, factory, magasinier):
        request = factory.get(RETOUR_URL.format(pk=999999))
        force_authenticate(request, user=magasinier)

        response = ReservationRetourView.as_view()(request, pk=999999)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestRetourEndpointPost:
    @pytest.mark.django_db
    def test_post_retour_partiel_ne_cloture_pas(
        self, factory, magasinier, reservation_livree, deux_lignes
    ):
        ligne_tente, ligne_chaise = deux_lignes
        request = factory.post(
            RETOUR_URL.format(pk=reservation_livree.pk),
            {
                "lignes": [
                    {"id": ligne_tente.pk, "quantite_rendue": 2},
                    {"id": ligne_chaise.pk, "quantite_rendue": 0},
                ]
            },
            format="json",
        )
        force_authenticate(request, user=magasinier)

        response = ReservationRetourView.as_view()(request, pk=reservation_livree.pk)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["statut_retour"] == "partiel"

        reservation_livree.refresh_from_db()
        ligne_tente.refresh_from_db()
        assert reservation_livree.statut == StatutReservation.LIVREE
        assert ligne_tente.quantite_retournee == 2

    @pytest.mark.django_db
    def test_post_retour_complet_transitionne_vers_retournee(
        self, factory, magasinier, reservation_livree, deux_lignes
    ):
        ligne_tente, ligne_chaise = deux_lignes
        request = factory.post(
            RETOUR_URL.format(pk=reservation_livree.pk),
            {
                "lignes": [
                    {"id": ligne_tente.pk, "quantite_rendue": 5},
                    {"id": ligne_chaise.pk, "quantite_rendue": 10},
                ]
            },
            format="json",
        )
        force_authenticate(request, user=magasinier)

        response = ReservationRetourView.as_view()(request, pk=reservation_livree.pk)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["statut_retour"] == "complet"
        assert response.data["statut"] == StatutReservation.RETOURNEE

        reservation_livree.refresh_from_db()
        assert reservation_livree.statut == StatutReservation.RETOURNEE

    @pytest.mark.django_db
    def test_post_peut_se_faire_en_plusieurs_fois(
        self, factory, magasinier, reservation_livree, deux_lignes
    ):
        ligne_tente, ligne_chaise = deux_lignes

        first = factory.post(
            RETOUR_URL.format(pk=reservation_livree.pk),
            {"lignes": [{"id": ligne_tente.pk, "quantite_rendue": 3}]},
            format="json",
        )
        force_authenticate(first, user=magasinier)
        ReservationRetourView.as_view()(first, pk=reservation_livree.pk)

        second = factory.post(
            RETOUR_URL.format(pk=reservation_livree.pk),
            {
                "lignes": [
                    {"id": ligne_tente.pk, "quantite_rendue": 5},
                    {"id": ligne_chaise.pk, "quantite_rendue": 10},
                ]
            },
            format="json",
        )
        force_authenticate(second, user=magasinier)
        response = ReservationRetourView.as_view()(second, pk=reservation_livree.pk)

        assert response.data["statut_retour"] == "complet"
        reservation_livree.refresh_from_db()
        assert reservation_livree.statut == StatutReservation.RETOURNEE

    @pytest.mark.django_db
    def test_post_quantite_superieure_a_demandee_renvoie_400(
        self, factory, magasinier, reservation_livree, deux_lignes
    ):
        ligne_tente, _ligne_chaise = deux_lignes
        request = factory.post(
            RETOUR_URL.format(pk=reservation_livree.pk),
            {"lignes": [{"id": ligne_tente.pk, "quantite_rendue": 99}]},
            format="json",
        )
        force_authenticate(request, user=magasinier)

        response = ReservationRetourView.as_view()(request, pk=reservation_livree.pk)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert str(ligne_tente.pk) in response.data["lignes"]

        ligne_tente.refresh_from_db()
        assert ligne_tente.quantite_retournee == 0

    @pytest.mark.django_db
    def test_post_ligne_hors_reservation_renvoie_400(
        self, factory, magasinier, reservation_livree, deux_lignes, prestation
    ):
        autre_part = Part.objects.create(name="Barnum")
        autre_reservation = Reservation.objects.create(
            prestation=prestation,
            demandeur=magasinier,
            statut=StatutReservation.LIVREE,
            date_demande=timezone.now(),
        )
        autre_ligne = LigneReservation.objects.create(
            reservation=autre_reservation,
            part=autre_part,
            quantite_demandee=1,
        )

        request = factory.post(
            RETOUR_URL.format(pk=reservation_livree.pk),
            {"lignes": [{"id": autre_ligne.pk, "quantite_rendue": 1}]},
            format="json",
        )
        force_authenticate(request, user=magasinier)

        response = ReservationRetourView.as_view()(request, pk=reservation_livree.pk)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_post_refuse_si_statut_incompatible(self, factory, magasinier, prestation):
        reservation = Reservation.objects.create(
            prestation=prestation,
            demandeur=magasinier,
            statut=StatutReservation.SOUMISE,
            date_demande=timezone.now(),
        )
        request = factory.post(
            RETOUR_URL.format(pk=reservation.pk),
            {"lignes": []},
            format="json",
        )
        force_authenticate(request, user=magasinier)

        response = ReservationRetourView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_409_CONFLICT


class TestRetourEndpointGardeFous:
    """Défauts relevés en revue : bon rouvert, doublons, atomicité."""

    @pytest.mark.django_db
    def test_post_refuse_sur_un_bon_deja_retourne(
        self, factory, magasinier, reservation_livree, deux_lignes
    ):
        ligne_tente, ligne_chaise = deux_lignes

        complet = factory.post(
            RETOUR_URL.format(pk=reservation_livree.pk),
            {
                "lignes": [
                    {"id": ligne_tente.pk, "quantite_rendue": 5},
                    {"id": ligne_chaise.pk, "quantite_rendue": 10},
                ]
            },
            format="json",
        )
        force_authenticate(complet, user=magasinier)
        ReservationRetourView.as_view()(complet, pk=reservation_livree.pk)

        reservation_livree.refresh_from_db()
        assert reservation_livree.statut == StatutReservation.RETOURNEE

        # Rouvrir le bon pour baisser les quantités laissait un état
        # « retournee / partiel » sans retour arrière possible.
        correction = factory.post(
            RETOUR_URL.format(pk=reservation_livree.pk),
            {"lignes": [{"id": ligne_tente.pk, "quantite_rendue": 2}]},
            format="json",
        )
        force_authenticate(correction, user=magasinier)

        response = ReservationRetourView.as_view()(
            correction, pk=reservation_livree.pk
        )

        assert response.status_code == status.HTTP_409_CONFLICT

        ligne_tente.refresh_from_db()
        assert ligne_tente.quantite_retournee == 5

    @pytest.mark.django_db
    def test_get_reste_consultable_sur_un_bon_retourne(
        self, factory, magasinier, reservation_livree, deux_lignes
    ):
        reservation_livree.statut = StatutReservation.RETOURNEE
        reservation_livree.save(update_fields=["statut"])

        request = factory.get(RETOUR_URL.format(pk=reservation_livree.pk))
        force_authenticate(request, user=magasinier)

        response = ReservationRetourView.as_view()(
            request, pk=reservation_livree.pk
        )

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.django_db
    def test_post_refuse_une_ligne_en_double(
        self, factory, magasinier, reservation_livree, deux_lignes
    ):
        ligne_tente, _ = deux_lignes

        request = factory.post(
            RETOUR_URL.format(pk=reservation_livree.pk),
            {
                "lignes": [
                    {"id": ligne_tente.pk, "quantite_rendue": 5},
                    {"id": ligne_tente.pk, "quantite_rendue": 1},
                ]
            },
            format="json",
        )
        force_authenticate(request, user=magasinier)

        response = ReservationRetourView.as_view()(
            request, pk=reservation_livree.pk
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        ligne_tente.refresh_from_db()
        assert ligne_tente.quantite_retournee == 0


class TestRetourPerimetrePhysique:
    """Un article virtuel n'a rien à rendre : il sort de la saisie retour."""

    @pytest.fixture
    def ligne_physique_et_service(self, db, reservation_livree):
        tente = Part.objects.create(name="Tente 4 places")
        service = Part.objects.create(name="Nettoyage")
        RentableItem.objects.create(part=service, is_virtual=True)

        physique = LigneReservation.objects.create(
            reservation=reservation_livree, part=tente, quantite_demandee=4
        )
        virtuelle = LigneReservation.objects.create(
            reservation=reservation_livree, part=service, quantite_demandee=1
        )
        return physique, virtuelle

    @pytest.mark.django_db
    def test_get_masque_la_ligne_virtuelle(
        self, factory, magasinier, reservation_livree, ligne_physique_et_service
    ):
        physique, virtuelle = ligne_physique_et_service

        request = factory.get("/plugin/inventree-location/reservations/1/retour/")
        force_authenticate(request, user=magasinier)
        response = ReservationRetourView.as_view()(request, pk=reservation_livree.pk)

        assert response.status_code == status.HTTP_200_OK
        ids = [ligne["id"] for ligne in response.data["lignes"]]
        assert ids == [physique.pk]
        assert virtuelle.pk not in ids
        assert response.data["quantite_demandee_totale"] == 4

    @pytest.mark.django_db
    def test_rendre_tout_le_materiel_donne_un_retour_complet(
        self, factory, magasinier, reservation_livree, ligne_physique_et_service
    ):
        physique, _virtuelle = ligne_physique_et_service

        request = factory.post(
            "/plugin/inventree-location/reservations/1/retour/",
            {"lignes": [{"id": physique.pk, "quantite_rendue": 4}]},
            format="json",
        )
        force_authenticate(request, user=magasinier)
        response = ReservationRetourView.as_view()(request, pk=reservation_livree.pk)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["statut_retour"] == "complet"

        reservation_livree.refresh_from_db()
        assert reservation_livree.statut == StatutReservation.RETOURNEE

    @pytest.mark.django_db
    def test_declarer_la_ligne_virtuelle_est_refuse(
        self, factory, magasinier, reservation_livree, ligne_physique_et_service
    ):
        _physique, virtuelle = ligne_physique_et_service

        request = factory.post(
            "/plugin/inventree-location/reservations/1/retour/",
            {"lignes": [{"id": virtuelle.pk, "quantite_rendue": 1}]},
            format="json",
        )
        force_authenticate(request, user=magasinier)
        response = ReservationRetourView.as_view()(request, pk=reservation_livree.pk)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert str(virtuelle.pk) in response.data["lignes"]
