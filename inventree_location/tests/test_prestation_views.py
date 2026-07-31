"""Tests des vues Prestation (ORG-01 / ORG-02 / RES-09 / STK-01).

Couvre le CRUD prestation, le rattachement à un lieu unique géolocalisé, la
liste d'articles + quantités imbriquée, la validation des dates dans la
manifestation et le blocage sur stock insuffisant.
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
    LignePrestation,
    Lieu,
    Manifestation,
    Prestation,
    RentableItem,
    StatutManifestation,
)
from inventree_location.views import (
    PrestationDetailView,
    PrestationListCreateView,
)

User = get_user_model()

PRESTATIONS_URL = "/plugin/inventree-location/prestations/"


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
def manifestation(db, user):
    now = timezone.now().replace(microsecond=0)
    groupe = Groupe.objects.create(nom="Jambville", code="JAM")
    return Manifestation.objects.create(
        nom="Camp été 2026",
        date_debut=now,
        date_fin=now + timedelta(days=7),
        organisateur=user,
        groupe=groupe,
    )


@pytest.fixture
def lieu(db):
    return Lieu.objects.create(nom="Terrain central", adresse="1 rue du camp")


@pytest.fixture
def prestation(manifestation, lieu):
    presta = Prestation.objects.create(
        manifestation=manifestation,
        lieu=lieu,
        nom="Installation",
        date_debut=manifestation.date_debut,
        date_fin=manifestation.date_debut + timedelta(hours=4),
    )
    return presta


def _make_part(name, *, stock=0, virtual=False):
    from part.models import Part

    part = Part.objects.create(name=name)
    RentableItem.objects.create(part=part, stock_total=stock, is_virtual=virtual)
    return part


class TestPrestationListView:
    def test_anonymous_returns_401(self, factory):
        request = factory.get(PRESTATIONS_URL)
        response = PrestationListCreateView.as_view()(request)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_list_includes_manifestation_and_lieu(self, factory, user, prestation):
        request = factory.get(PRESTATIONS_URL)
        force_authenticate(request, user=user)
        response = PrestationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        row = response.data["results"][0]
        assert row["nom"] == "Installation"
        assert row["manifestation_nom"] == "Camp été 2026"
        assert row["lieu_detail"]["nom"] == "Terrain central"

    @pytest.mark.django_db
    def test_filter_by_manifestation(self, factory, user, prestation, manifestation):
        request = factory.get(PRESTATIONS_URL, {"manifestation": manifestation.pk})
        force_authenticate(request, user=user)
        response = PrestationListCreateView.as_view()(request)
        assert len(response.data["results"]) == 1

        request = factory.get(PRESTATIONS_URL, {"manifestation": manifestation.pk + 9})
        force_authenticate(request, user=user)
        response = PrestationListCreateView.as_view()(request)
        assert len(response.data["results"]) == 0

    @pytest.mark.django_db
    def test_search_by_nom(self, factory, user, prestation):
        request = factory.get(PRESTATIONS_URL, {"search": "installation"})
        force_authenticate(request, user=user)
        response = PrestationListCreateView.as_view()(request)
        assert len(response.data["results"]) == 1

        request = factory.get(PRESTATIONS_URL, {"search": "introuvable"})
        force_authenticate(request, user=user)
        response = PrestationListCreateView.as_view()(request)
        assert len(response.data["results"]) == 0


@pytest.mark.django_db
class TestPrestationCreate:
    def test_create_with_lignes(self, factory, user, manifestation, lieu):
        part = _make_part("Tente 6 places", stock=10)
        payload = {
            "manifestation": manifestation.pk,
            "lieu": lieu.pk,
            "nom": "Montage",
            "date_debut": manifestation.date_debut.isoformat(),
            "date_fin": (manifestation.date_debut + timedelta(hours=2)).isoformat(),
            "lignes": [{"part": part.pk, "quantite": 4}],
        }
        request = factory.post(PRESTATIONS_URL, payload, format="json")
        force_authenticate(request, user=user)
        response = PrestationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED, response.data
        presta = Prestation.objects.get(nom="Montage")
        assert presta.lieu_id == lieu.pk
        assert LignePrestation.objects.filter(prestation=presta).count() == 1

    def test_same_day_earlier_hour_accepted(self, factory, user, manifestation, lieu):
        # Même jour que la manif, heure antérieure : accepté (bornage au jour).
        # Minuit local pour éviter un basculement de date à minuit.
        earlier = timezone.localtime(manifestation.date_debut).replace(
            hour=0, minute=0, second=0
        )
        payload = {
            "manifestation": manifestation.pk,
            "lieu": lieu.pk,
            "nom": "Montage matinal",
            "date_debut": earlier.isoformat(),
            "date_fin": (earlier + timedelta(hours=2)).isoformat(),
        }
        request = factory.post(PRESTATIONS_URL, payload, format="json")
        force_authenticate(request, user=user)
        response = PrestationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED, response.data

    def test_dates_outside_manifestation_rejected(
        self, factory, user, manifestation, lieu
    ):
        payload = {
            "manifestation": manifestation.pk,
            "lieu": lieu.pk,
            "nom": "Hors période",
            "date_debut": (manifestation.date_debut - timedelta(days=1)).isoformat(),
            "date_fin": manifestation.date_fin.isoformat(),
        }
        request = factory.post(PRESTATIONS_URL, payload, format="json")
        force_authenticate(request, user=user)
        response = PrestationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "date_debut" in response.data

    def test_creation_blocked_when_manifestation_started(
        self, factory, user, manifestation, lieu
    ):
        # Manif planifiée dont la date de début est passée → effectif en_cours
        # → on ne peut plus y ajouter de prestation.
        now = timezone.now()
        manifestation.statut = StatutManifestation.PLANIFIEE
        manifestation.date_debut = now - timedelta(hours=1)
        manifestation.date_fin = now + timedelta(days=3)
        manifestation.save()

        payload = {
            "manifestation": manifestation.pk,
            "lieu": lieu.pk,
            "nom": "Trop tard",
            "date_debut": now.isoformat(),
            "date_fin": (now + timedelta(hours=2)).isoformat(),
        }
        request = factory.post(PRESTATIONS_URL, payload, format="json")
        force_authenticate(request, user=user)
        response = PrestationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "manifestation" in response.data
        assert not Prestation.objects.filter(nom="Trop tard").exists()

    def test_insufficient_stock_blocks_creation(
        self, factory, user, manifestation, lieu
    ):
        part = _make_part("Chaise", stock=3)
        payload = {
            "manifestation": manifestation.pk,
            "lieu": lieu.pk,
            "nom": "Trop de chaises",
            "date_debut": manifestation.date_debut.isoformat(),
            "date_fin": (manifestation.date_debut + timedelta(hours=2)).isoformat(),
            "lignes": [{"part": part.pk, "quantite": 5}],
        }
        request = factory.post(PRESTATIONS_URL, payload, format="json")
        force_authenticate(request, user=user)
        response = PrestationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "stock" in response.data
        assert not Prestation.objects.filter(nom="Trop de chaises").exists()


@pytest.mark.django_db
class TestPrestationDetail:
    def test_update_replaces_lignes(self, factory, user, prestation):
        part = _make_part("Table", stock=20)
        payload = {"lignes": [{"part": part.pk, "quantite": 2}]}
        request = factory.patch(
            f"{PRESTATIONS_URL}{prestation.pk}/", payload, format="json"
        )
        force_authenticate(request, user=user)
        response = PrestationDetailView.as_view()(request, pk=prestation.pk)

        assert response.status_code == status.HTTP_200_OK, response.data
        assert prestation.lignes_prestation.count() == 1

    def test_delete(self, factory, user, prestation):
        request = factory.delete(f"{PRESTATIONS_URL}{prestation.pk}/")
        force_authenticate(request, user=user)
        response = PrestationDetailView.as_view()(request, pk=prestation.pk)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Prestation.objects.filter(pk=prestation.pk).exists()
