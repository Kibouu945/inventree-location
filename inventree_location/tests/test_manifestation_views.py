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

    def test_anonymous_returns_401(self, factory):
        request = factory.get("/plugin/inventree-location/groupes/")
        response = ClientListView.as_view()(request)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
