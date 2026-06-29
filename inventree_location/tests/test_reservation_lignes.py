"""Tests RES-02 : filtres (statut/période) et lignes imbriquées des réservations."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location.models import (
    Groupe,
    LigneReservation,
    Manifestation,
    Prestation,
    Reservation,
)
from inventree_location.views import (
    ReservationDetailView,
    ReservationListCreateView,
)

from part.models import Part

User = get_user_model()

RESA_URL = "/plugin/inventree-location/reservations/"


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def user(db):
    from django.contrib.auth.models import Group

    from inventree_location import roles

    account = User.objects.create_user(username="alice", password="pwd12345")
    account.groups.add(Group.objects.get(name=roles.GESTIONNAIRE))
    return account


@pytest.fixture
def prestation(db, user):
    groupe = Groupe.objects.create(nom="Jambville", code="JAM")
    now = timezone.now()
    manifestation = Manifestation.objects.create(
        nom="Camp été 2026",
        date_debut=now,
        date_fin=now + timedelta(days=7),
        organisateur=user,
        groupe=groupe,
    )
    return Prestation.objects.create(
        manifestation=manifestation,
        nom="Installation",
        date_debut=now,
        date_fin=now + timedelta(hours=4),
    )


@pytest.fixture
def part(db):
    return Part.objects.create(name="Tente 4 places")


class TestReservationFilters:
    @pytest.mark.django_db
    def test_filter_by_statut(self, factory, user, prestation):
        Reservation.objects.create(
            prestation=prestation,
            demandeur=user,
            date_demande=timezone.now(),
            statut="brouillon",
        )
        validee = Reservation.objects.create(
            prestation=prestation,
            demandeur=user,
            date_demande=timezone.now(),
            statut="validee",
        )

        request = factory.get(RESA_URL, {"statut": "validee"})
        force_authenticate(request, user=user)
        response = ReservationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert [row["id"] for row in response.data] == [validee.pk]

    @pytest.mark.django_db
    def test_filter_by_period(self, factory, user, prestation):
        base = timezone.now().replace(microsecond=0)
        early = Reservation.objects.create(
            prestation=prestation,
            demandeur=user,
            date_demande=base,
            date_retrait_prevue=base,
            date_retour_prevue=base + timedelta(days=1),
        )
        # Hors fenêtre : commence après date_to.
        Reservation.objects.create(
            prestation=prestation,
            demandeur=user,
            date_demande=base,
            date_retrait_prevue=base + timedelta(days=10),
            date_retour_prevue=base + timedelta(days=12),
        )

        request = factory.get(
            RESA_URL,
            {
                "date_from": base.isoformat(),
                "date_to": (base + timedelta(days=2)).isoformat(),
            },
        )
        force_authenticate(request, user=user)
        response = ReservationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert [row["id"] for row in response.data] == [early.pk]


class TestReservationNestedLignes:
    @pytest.mark.django_db
    def test_create_with_nested_lignes(self, factory, user, prestation, part):
        payload = {
            "prestation": prestation.pk,
            "demandeur": user.pk,
            "date_demande": timezone.now().isoformat(),
            "lignes": [
                {"part": part.pk, "quantite_demandee": 3},
            ],
        }
        request = factory.post(RESA_URL, payload, format="json")
        force_authenticate(request, user=user)

        response = ReservationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED
        reservation = Reservation.objects.get()
        ligne = reservation.lignes.get()
        assert ligne.part_id == part.pk
        assert ligne.quantite_demandee == 3
        assert response.data["lignes"][0]["quantite_demandee"] == 3

    @pytest.mark.django_db
    def test_patch_replaces_lignes(self, factory, user, prestation, part):
        reservation = Reservation.objects.create(
            prestation=prestation,
            demandeur=user,
            date_demande=timezone.now(),
        )
        LigneReservation.objects.create(
            reservation=reservation, part=part, quantite_demandee=1
        )

        payload = {"lignes": [{"part": part.pk, "quantite_demandee": 5}]}
        request = factory.patch(f"{RESA_URL}{reservation.pk}/", payload, format="json")
        force_authenticate(request, user=user)

        response = ReservationDetailView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_200_OK
        ligne = reservation.lignes.get()
        assert ligne.quantite_demandee == 5
