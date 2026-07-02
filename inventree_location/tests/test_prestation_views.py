"""Tests de `PrestationListView` : lecture seule, recherche, lieux imbriqués."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location.models import Groupe, Lieu, Manifestation, Prestation
from inventree_location.views import PrestationListView

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
def prestation(db, user):
    now = timezone.now().replace(microsecond=0)
    groupe = Groupe.objects.create(nom="Jambville", code="JAM")
    manifestation = Manifestation.objects.create(
        nom="Camp été 2026",
        date_debut=now,
        date_fin=now + timedelta(days=7),
        organisateur=user,
        groupe=groupe,
    )
    prestation = Prestation.objects.create(
        manifestation=manifestation,
        nom="Installation",
        date_debut=now,
        date_fin=now + timedelta(hours=4),
    )
    Lieu.objects.create(prestation=prestation, nom="Terrain central")
    return prestation


class TestPrestationListView:
    def test_anonymous_returns_401(self, factory):
        request = factory.get(PRESTATIONS_URL)
        response = PrestationListView.as_view()(request)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_list_includes_manifestation_and_lieux(self, factory, user, prestation):
        request = factory.get(PRESTATIONS_URL)
        force_authenticate(request, user=user)
        response = PrestationListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        row = response.data["results"][0]
        assert row["nom"] == "Installation"
        assert row["manifestation_nom"] == "Camp été 2026"
        assert [lieu["nom"] for lieu in row["lieux"]] == ["Terrain central"]

    @pytest.mark.django_db
    def test_search_by_nom(self, factory, user, prestation):
        request = factory.get(PRESTATIONS_URL, {"search": "installation"})
        force_authenticate(request, user=user)
        response = PrestationListView.as_view()(request)
        assert len(response.data["results"]) == 1

        request = factory.get(PRESTATIONS_URL, {"search": "introuvable"})
        force_authenticate(request, user=user)
        response = PrestationListView.as_view()(request)
        assert len(response.data["results"]) == 0

    @pytest.mark.django_db
    def test_search_by_manifestation_nom(self, factory, user, prestation):
        request = factory.get(PRESTATIONS_URL, {"search": "camp été"})
        force_authenticate(request, user=user)
        response = PrestationListView.as_view()(request)
        assert len(response.data["results"]) == 1
