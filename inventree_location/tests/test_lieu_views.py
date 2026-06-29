"""Tests des endpoints de gestion des lieux et du géocodage (SCRUM-62).

Couvre :
- `LieuListCreateView`   : liste, filtres (`prestation`, `search`), création ;
- `LieuDetailView`       : lecture, mise à jour des coordonnées GPS, suppression ;
- `LieuSerializer`       : validation des bornes latitude/longitude ;
- `GeocodeAddressView`   : appel Nominatim mocké (succès / aucun résultat /
  service indisponible) et validation du paramètre `address`.

On suit le même pattern que `test_views.py` : `APIRequestFactory` +
`force_authenticate`, sans dépendre du routeur d'InvenTree.
"""

from __future__ import annotations

from datetime import timedelta
from urllib.error import URLError

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location.models import Groupe, Lieu, Manifestation, Prestation
from inventree_location.views import (
    GeocodeAddressView,
    LieuDetailView,
    LieuListCreateView,
)

User = get_user_model()

LIEUX_URL = "/plugin/inventree-location/lieux/"
GEOCODE_URL = "/plugin/inventree-location/geocode/"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    now = timezone.now()
    groupe = Groupe.objects.create(nom="Jambville", code="JAM")
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
def lieu(prestation):
    return Lieu.objects.create(
        prestation=prestation,
        nom="Terrain central",
        adresse="1 rue du camp",
        latitude="48.856600",
        longitude="2.352200",
        capacite=120,
    )


class _FakeNominatimResponse:
    """Faux objet réponse compatible `with urlopen(...) as response`."""

    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------


class TestLieuAuth:
    def test_list_anonymous_returns_401(self, factory):
        request = factory.get(LIEUX_URL)
        response = LieuListCreateView.as_view()(request)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_geocode_anonymous_returns_401(self, factory):
        request = factory.get(GEOCODE_URL, {"address": "Paris"})
        response = GeocodeAddressView.as_view()(request)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Liste / filtres / création
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLieuListCreate:
    def test_list_returns_existing_lieu(self, factory, user, lieu):
        request = factory.get(LIEUX_URL)
        force_authenticate(request, user=user)
        response = LieuListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["nom"] == "Terrain central"

    def test_filter_by_prestation(self, factory, user, lieu, prestation):
        request = factory.get(LIEUX_URL, {"prestation": prestation.pk})
        force_authenticate(request, user=user)
        response = LieuListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

        request = factory.get(LIEUX_URL, {"prestation": prestation.pk + 999})
        force_authenticate(request, user=user)
        response = LieuListCreateView.as_view()(request)
        assert len(response.data["results"]) == 0

    def test_search_by_name(self, factory, user, lieu):
        request = factory.get(LIEUX_URL, {"search": "central"})
        force_authenticate(request, user=user)
        response = LieuListCreateView.as_view()(request)
        assert len(response.data["results"]) == 1

        request = factory.get(LIEUX_URL, {"search": "introuvable"})
        force_authenticate(request, user=user)
        response = LieuListCreateView.as_view()(request)
        assert len(response.data["results"]) == 0

    def test_create_persists_lieu(self, factory, user, prestation):
        payload = {
            "prestation": prestation.pk,
            "nom": "Entrée nord",
            "adresse": "Porte A",
            "latitude": "45.764000",
            "longitude": "4.835700",
            "capacite": 50,
        }
        request = factory.post(LIEUX_URL, payload, format="json")
        force_authenticate(request, user=user)
        response = LieuListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert Lieu.objects.filter(nom="Entrée nord").exists()


# ---------------------------------------------------------------------------
# Validation des coordonnées
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLieuSerializerValidation:
    @pytest.mark.parametrize(
        "field,value",
        [
            ("latitude", "91.000000"),
            ("latitude", "-91.000000"),
            ("longitude", "181.000000"),
            ("longitude", "-181.000000"),
        ],
    )
    def test_out_of_range_coordinates_rejected(
        self, factory, user, prestation, field, value
    ):
        payload = {"prestation": prestation.pk, "nom": "Hors bornes", field: value}
        request = factory.post(LIEUX_URL, payload, format="json")
        force_authenticate(request, user=user)
        response = LieuListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert field in response.data


# ---------------------------------------------------------------------------
# Détail : lecture / mise à jour GPS / suppression
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLieuDetail:
    def test_retrieve(self, factory, user, lieu):
        request = factory.get(f"{LIEUX_URL}{lieu.pk}/")
        force_authenticate(request, user=user)
        response = LieuDetailView.as_view()(request, pk=lieu.pk)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == lieu.pk

    def test_patch_updates_coordinates(self, factory, user, lieu):
        request = factory.patch(
            f"{LIEUX_URL}{lieu.pk}/",
            {"latitude": "43.296500", "longitude": "5.369800"},
            format="json",
        )
        force_authenticate(request, user=user)
        response = LieuDetailView.as_view()(request, pk=lieu.pk)

        assert response.status_code == status.HTTP_200_OK
        lieu.refresh_from_db()
        assert str(lieu.latitude) == "43.296500"
        assert str(lieu.longitude) == "5.369800"

    def test_delete(self, factory, user, lieu):
        request = factory.delete(f"{LIEUX_URL}{lieu.pk}/")
        force_authenticate(request, user=user)
        response = LieuDetailView.as_view()(request, pk=lieu.pk)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Lieu.objects.filter(pk=lieu.pk).exists()


# ---------------------------------------------------------------------------
# Géocodage (Nominatim mocké)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGeocodeAddressView:
    def test_missing_address_returns_400(self, factory, user):
        request = factory.get(GEOCODE_URL)
        force_authenticate(request, user=user)
        response = GeocodeAddressView.as_view()(request)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_success_returns_coordinates(self, factory, user, monkeypatch):
        body = b'[{"display_name": "Paris, France", "lat": "48.8566", "lon": "2.3522"}]'
        monkeypatch.setattr(
            "inventree_location.serializers.urlopen",
            lambda *a, **k: _FakeNominatimResponse(body),
        )

        request = factory.get(GEOCODE_URL, {"address": "Paris"})
        force_authenticate(request, user=user)
        response = GeocodeAddressView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["latitude"] == "48.8566"
        assert response.data["longitude"] == "2.3522"
        assert response.data["source"] == "OpenStreetMap Nominatim"

    def test_no_result_returns_404(self, factory, user, monkeypatch):
        monkeypatch.setattr(
            "inventree_location.serializers.urlopen",
            lambda *a, **k: _FakeNominatimResponse(b"[]"),
        )
        request = factory.get(GEOCODE_URL, {"address": "zzzznowhere"})
        force_authenticate(request, user=user)
        response = GeocodeAddressView.as_view()(request)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_service_error_returns_503(self, factory, user, monkeypatch):
        def _boom(*a, **k):
            raise URLError("nominatim down")

        monkeypatch.setattr("inventree_location.serializers.urlopen", _boom)
        request = factory.get(GEOCODE_URL, {"address": "Paris"})
        force_authenticate(request, user=user)
        response = GeocodeAddressView.as_view()(request)
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
