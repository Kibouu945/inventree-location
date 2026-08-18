"""Tests du check-in retour ligne par ligne (SCRUM-94).

Endpoint ``reservations/<pk>/checkin/`` :
- GET  : accessible uniquement quand la réservation est au statut livrée.
- POST : valide somme(ok + manquant + casse) == quantité demandée par ligne,
  journalise les incidents, puis clôture la réservation.
"""

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
    Groupe,
    LigneReservation,
    Manifestation,
    Prestation,
    Reservation,
    StatutReservation,
)
from inventree_location.views import ReservationCheckinView

User = get_user_model()

CHECKIN_URL = "/plugin/inventree-location/reservations/{pk}/checkin/"


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
    groupe = Groupe.objects.create(nom="Jambville", code="JAM")
    manifestation = Manifestation.objects.create(
        nom="Camp été 2026",
        date_debut=now,
        date_fin=now + timedelta(days=7),
        organisateur=magasinier,
        groupe=groupe,
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
def ligne(db, reservation_livree):
    part = Part.objects.create(name="Tente 4 places")
    return LigneReservation.objects.create(
        reservation=reservation_livree,
        part=part,
        quantite_demandee=5,
    )


class TestCheckinEndpointGet:
    @pytest.mark.django_db
    def test_get_renvoie_les_lignes_si_livree(
        self, factory, magasinier, reservation_livree, ligne
    ):
        request = factory.get(CHECKIN_URL.format(pk=reservation_livree.pk))
        force_authenticate(request, user=magasinier)

        response = ReservationCheckinView.as_view()(
            request, pk=reservation_livree.pk
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["statut"] == StatutReservation.LIVREE
        assert len(response.data["lignes"]) == 1
        assert response.data["lignes"][0]["quantite_demandee"] == 5

    @pytest.mark.django_db
    def test_get_refuse_si_statut_different_de_livree(
        self, factory, magasinier, prestation
    ):
        reservation = Reservation.objects.create(
            prestation=prestation,
            demandeur=magasinier,
            statut=StatutReservation.SOUMISE,
            date_demande=timezone.now(),
        )
        request = factory.get(CHECKIN_URL.format(pk=reservation.pk))
        force_authenticate(request, user=magasinier)

        response = ReservationCheckinView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.django_db
    def test_get_reservation_introuvable_renvoie_404(self, factory, magasinier):
        request = factory.get(CHECKIN_URL.format(pk=999999))
        force_authenticate(request, user=magasinier)

        response = ReservationCheckinView.as_view()(request, pk=999999)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestCheckinEndpointPost:
    @pytest.mark.django_db
    def test_post_valide_cloture_la_reservation(
        self, factory, magasinier, reservation_livree, ligne
    ):
        request = factory.post(
            CHECKIN_URL.format(pk=reservation_livree.pk),
            {"lignes": [{"id": ligne.pk, "ok": 4, "manquant": 1, "casse": 0}]},
            format="json",
        )
        force_authenticate(request, user=magasinier)

        response = ReservationCheckinView.as_view()(
            request, pk=reservation_livree.pk
        )

        assert response.status_code == status.HTTP_200_OK

        reservation_livree.refresh_from_db()
        ligne.refresh_from_db()
        assert reservation_livree.statut == StatutReservation.CLOTUREE
        assert ligne.quantite_retour_ok == 4
        assert ligne.quantite_retour_manquant == 1
        assert ligne.etat_retour == "manquant"

    @pytest.mark.django_db
    def test_post_somme_incorrecte_renvoie_400_sans_effet(
        self, factory, magasinier, reservation_livree, ligne
    ):
        request = factory.post(
            CHECKIN_URL.format(pk=reservation_livree.pk),
            {"lignes": [{"id": ligne.pk, "ok": 2, "manquant": 1, "casse": 0}]},
            format="json",
        )
        force_authenticate(request, user=magasinier)

        response = ReservationCheckinView.as_view()(
            request, pk=reservation_livree.pk
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert str(ligne.pk) in response.data["lignes"]

        reservation_livree.refresh_from_db()
        assert reservation_livree.statut == StatutReservation.LIVREE

    @pytest.mark.django_db
    def test_post_casse_journalise_incident_et_ligne_cassee(
        self, factory, magasinier, reservation_livree, ligne
    ):
        request = factory.post(
            CHECKIN_URL.format(pk=reservation_livree.pk),
            {
                "lignes": [
                    {
                        "id": ligne.pk,
                        "ok": 3,
                        "manquant": 0,
                        "casse": 2,
                        "commentaire": "Toile déchirée",
                    }
                ]
            },
            format="json",
        )
        force_authenticate(request, user=magasinier)

        response = ReservationCheckinView.as_view()(
            request, pk=reservation_livree.pk
        )

        assert response.status_code == status.HTTP_200_OK

        ligne.refresh_from_db()
        assert ligne.etat_retour == "casse"
        assert ligne.commentaire == "Toile déchirée"
        assert ligne.quantite_retournee == 5

    @pytest.mark.django_db
    def test_post_refuse_si_statut_different_de_livree(
        self, factory, magasinier, prestation
    ):
        reservation = Reservation.objects.create(
            prestation=prestation,
            demandeur=magasinier,
            statut=StatutReservation.SOUMISE,
            date_demande=timezone.now(),
        )
        request = factory.post(
            CHECKIN_URL.format(pk=reservation.pk),
            {"lignes": []},
            format="json",
        )
        force_authenticate(request, user=magasinier)

        response = ReservationCheckinView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_409_CONFLICT
