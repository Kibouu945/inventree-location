"""Tests d'authentification sur les vues du plugin.

Le plugin réutilise l'auth d'InvenTree (DRF Token). Ce test garde-fou s'assure
que toutes les vues exposées par le plugin restent verrouillées derrière
`IsAuthenticated`, peu importe la façon dont elles évoluent.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location.views import ExampleView


User = get_user_model()


@pytest.fixture
def factory():
    return APIRequestFactory()


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
