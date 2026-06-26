"""Tests de la vue catalogue et du bulk-update du drapeau louable.

Hors container InvenTree, `part.Part` est l'app factice (cf. tests/part/).
On y crée des Part + PartCategory pour exercer filtres, pagination et le
câblage du drapeau louable sur RentableItem.
"""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from django.contrib.auth import get_user_model

from inventree_location.models import RentableItem
from inventree_location.views import (
    CatalogPagination,
    CatalogPartListView,
    RentableFlagBulkUpdateView,
)

from part.models import Part, PartCategory

User = get_user_model()

CATALOG_URL = "/plugin/inventree-location/catalog/"
BULK_URL = "/plugin/inventree-location/catalog/rentable/"


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", password="pwd12345")


@pytest.fixture
def categorie(db):
    return PartCategory.objects.create(name="Tentes")


@pytest.fixture
def parts(db, categorie):
    """Trois parts : un louable par défaut, un explicitement non-louable, un consommable."""

    tente = Part.objects.create(name="Tente 4 places", category=categorie)
    cle = Part.objects.create(name="Clé hexagonale", category=categorie)
    gobelet = Part.objects.create(name="Gobelet carton", category=categorie)

    # `tente` n'a pas de RentableItem -> louable par défaut.
    RentableItem.objects.create(part=cle, is_rentable=False)
    RentableItem.objects.create(part=gobelet, is_rentable=True, consommable=True)

    return {"tente": tente, "cle": cle, "gobelet": gobelet}


def _names(response):
    return {row["name"] for row in response.data["results"]}


class TestCatalogRentableFiltering:
    def test_anonymous_returns_401(self, factory):
        request = factory.get(CATALOG_URL)
        response = CatalogPartListView.as_view()(request)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_default_returns_rentable_only(self, factory, user, parts):
        request = factory.get(CATALOG_URL)
        force_authenticate(request, user=user)

        response = CatalogPartListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        # `cle` (is_rentable=False) est exclue ; `tente` (pas de flag) reste.
        assert _names(response) == {"Tente 4 places", "Gobelet carton"}

    @pytest.mark.django_db
    def test_rentable_all_returns_everything(self, factory, user, parts):
        request = factory.get(CATALOG_URL, {"rentable": "all"})
        force_authenticate(request, user=user)

        response = CatalogPartListView.as_view()(request)

        assert _names(response) == {
            "Tente 4 places",
            "Clé hexagonale",
            "Gobelet carton",
        }

    @pytest.mark.django_db
    def test_rentable_false_returns_non_rentable_only(self, factory, user, parts):
        request = factory.get(CATALOG_URL, {"rentable": "false"})
        force_authenticate(request, user=user)

        response = CatalogPartListView.as_view()(request)

        assert _names(response) == {"Clé hexagonale"}

    @pytest.mark.django_db
    def test_search_filters_by_name(self, factory, user, parts):
        request = factory.get(CATALOG_URL, {"search": "tente", "rentable": "all"})
        force_authenticate(request, user=user)

        response = CatalogPartListView.as_view()(request)

        assert _names(response) == {"Tente 4 places"}

    @pytest.mark.django_db
    def test_consommable_flag_is_exposed(self, factory, user, parts):
        request = factory.get(CATALOG_URL, {"rentable": "all"})
        force_authenticate(request, user=user)

        response = CatalogPartListView.as_view()(request)

        by_name = {row["name"]: row for row in response.data["results"]}
        assert by_name["Gobelet carton"]["consommable"] is True
        assert by_name["Tente 4 places"]["consommable"] is False
        assert by_name["Tente 4 places"]["rentable"] is True
        assert by_name["Clé hexagonale"]["rentable"] is False

    def test_pagination_page_size_is_50(self):
        # CAT-02 : la spec demande 50 éléments par page.
        assert CatalogPagination.page_size == 50


class TestRentableFlagBulkUpdate:
    def test_anonymous_returns_401(self, factory):
        request = factory.patch(BULK_URL, {}, format="json")
        response = RentableFlagBulkUpdateView.as_view()(request)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_bulk_sets_is_rentable_and_creates_rows(self, factory, user, parts):
        payload = {
            "part_ids": [parts["tente"].pk, parts["gobelet"].pk],
            "is_rentable": False,
        }
        request = factory.patch(BULK_URL, payload, format="json")
        force_authenticate(request, user=user)

        response = RentableFlagBulkUpdateView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        # `tente` n'avait pas de RentableItem -> créé à False.
        assert RentableItem.objects.get(part=parts["tente"]).is_rentable is False
        # `gobelet` existait -> mis à jour à False.
        assert RentableItem.objects.get(part=parts["gobelet"]).is_rentable is False

    @pytest.mark.django_db
    def test_empty_part_ids_returns_400(self, factory, user):
        request = factory.patch(BULK_URL, {"is_rentable": True}, format="json")
        force_authenticate(request, user=user)

        response = RentableFlagBulkUpdateView.as_view()(request)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_missing_flags_returns_400(self, factory, user, parts):
        request = factory.patch(
            BULK_URL, {"part_ids": [parts["tente"].pk]}, format="json"
        )
        force_authenticate(request, user=user)

        response = RentableFlagBulkUpdateView.as_view()(request)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
