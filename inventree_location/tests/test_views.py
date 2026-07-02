"""Tests d'authentification sur les vues du plugin.

Le plugin réutilise l'auth d'InvenTree (DRF Token). Ce test garde-fou s'assure
que toutes les vues exposées par le plugin restent verrouillées derrière
`IsAuthenticated`, peu importe la façon dont elles évoluent.
"""

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
    RentableItem,
    Reservation,
)
from inventree_location.views import (
    ExampleView,
    ReservationDetailView,
    ReservationListCreateView,
)

from part.models import Part


User = get_user_model()


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
def groupe(db):
    return Groupe.objects.create(nom="Jambville", code="JAM")


@pytest.fixture
def manifestation(user, groupe):
    now = timezone.now()
    return Manifestation.objects.create(
        nom="Camp été 2026",
        date_debut=now,
        date_fin=now + timedelta(days=7),
        organisateur=user,
        groupe=groupe,
    )


@pytest.fixture
def prestation(manifestation):
    return Prestation.objects.create(
        manifestation=manifestation,
        nom="Installation",
        date_debut=manifestation.date_debut,
        date_fin=manifestation.date_debut + timedelta(hours=4),
    )


@pytest.fixture
def reservation(prestation, user):
    return Reservation.objects.create(
        prestation=prestation,
        demandeur=user,
        date_demande=timezone.now(),
    )


class TestExampleViewAuth:
    def test_anonymous_request_returns_401(self, factory):
        request = factory.get("/plugin/inventree-location/example/")
        response = ExampleView.as_view()(request)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_authenticated_request_returns_200(self, factory):
        user = User.objects.create_user(username="alice", password="pwd12345")
        request = factory.get("/plugin/inventree-location/example/")
        force_authenticate(request, user=user)

        response = ExampleView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert "random_text" in response.data
        # Hors InvenTree : `part.Part` est l'app factice (cf. tests/part/),
        # la table est vide → 0. En production, c'est le vrai Part natif.
        assert response.data["part_count"] == 0


class TestPermissionClassesAreSet:
    def test_example_view_requires_authentication(self):
        from rest_framework.permissions import IsAuthenticated

        assert IsAuthenticated in ExampleView.permission_classes

    def test_reservation_list_create_view_uses_role_permission(self):
        from inventree_location.permissions import ReservationPermission

        assert ReservationPermission in ReservationListCreateView.permission_classes

    def test_reservation_detail_view_uses_role_permission(self):
        from inventree_location.permissions import ReservationPermission

        assert ReservationPermission in ReservationDetailView.permission_classes


# ---------------------------------------------------------------------------
# CRUD réservation — ReservationListCreateView (GET liste / POST création)
# ---------------------------------------------------------------------------


class TestReservationListCreateView:
    def test_anonymous_request_returns_401(self, factory):
        request = factory.get("/plugin/inventree-location/reservations/")
        response = ReservationListCreateView.as_view()(request)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_list_returns_existing_reservations(self, factory, user, reservation):
        request = factory.get("/plugin/inventree-location/reservations/")
        force_authenticate(request, user=user)

        response = ReservationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["id"] == reservation.pk

    @pytest.mark.django_db
    def test_create_reservation(self, factory, user, prestation):
        payload = {
            "prestation": prestation.pk,
            "demandeur": user.pk,
            "date_demande": timezone.now().isoformat(),
        }
        request = factory.post("/plugin/inventree-location/reservations/", payload)
        force_authenticate(request, user=user)

        response = ReservationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert Reservation.objects.count() == 1
        created = Reservation.objects.get()
        assert created.prestation_id == prestation.pk
        assert created.demandeur_id == user.pk
        # Le statut par défaut du modèle est appliqué si non fourni
        assert response.data["statut"] == "brouillon"

    @pytest.mark.django_db
    def test_create_reservation_missing_required_field_returns_400(
        self, factory, user, prestation
    ):
        # `demandeur` manque volontairement pour vérifier la validation DRF
        payload = {
            "prestation": prestation.pk,
            "date_demande": timezone.now().isoformat(),
        }
        request = factory.post("/plugin/inventree-location/reservations/", payload)
        force_authenticate(request, user=user)

        response = ReservationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "demandeur" in response.data


# ---------------------------------------------------------------------------
# CRUD réservation — ReservationDetailView (GET / PUT / PATCH / DELETE)
# ---------------------------------------------------------------------------


class TestReservationDetailView:
    def test_anonymous_request_returns_401(self, factory, db):
        request = factory.get("/plugin/inventree-location/reservations/1/")
        response = ReservationDetailView.as_view()(request, pk=1)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_retrieve_existing_reservation(self, factory, user, reservation):
        request = factory.get(
            f"/plugin/inventree-location/reservations/{reservation.pk}/"
        )
        force_authenticate(request, user=user)

        response = ReservationDetailView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == reservation.pk

    @pytest.mark.django_db
    def test_retrieve_missing_reservation_returns_404(self, factory, user):
        request = factory.get("/plugin/inventree-location/reservations/999/")
        force_authenticate(request, user=user)

        response = ReservationDetailView.as_view()(request, pk=999)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_patch_updates_statut(self, factory, user, reservation, prestation):
        # La soumission (RES-03) exige dates + au moins une ligne virtuelle :
        # on complète la réservation brouillon avant de la soumettre.
        reservation.date_retrait_prevue = prestation.date_debut
        reservation.date_retour_prevue = prestation.date_fin
        reservation.save()

        article_virtuel = Part.objects.create(name="Prestation nettoyage")
        RentableItem.objects.create(part=article_virtuel, is_virtual=True)
        LigneReservation.objects.create(
            reservation=reservation, part=article_virtuel, quantite_demandee=1
        )

        request = factory.patch(
            f"/plugin/inventree-location/reservations/{reservation.pk}/",
            {"statut": "soumise"},
        )
        force_authenticate(request, user=user)

        response = ReservationDetailView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_200_OK
        reservation.refresh_from_db()
        assert reservation.statut == "soumise"

    @pytest.mark.django_db
    def test_delete_removes_reservation(self, factory, user, reservation):
        request = factory.delete(
            f"/plugin/inventree-location/reservations/{reservation.pk}/"
        )
        force_authenticate(request, user=user)

        response = ReservationDetailView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Reservation.objects.filter(pk=reservation.pk).exists()
