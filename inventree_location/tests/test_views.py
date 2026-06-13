"""Tests d'authentification sur les vues du plugin.

Le plugin réutilise l'auth d'InvenTree (DRF Token). Ce test garde-fou s'assure
que toutes les vues exposées par le plugin restent verrouillées derrière
`IsAuthenticated`, peu importe la façon dont elles évoluent.
"""

from __future__ import annotations

from unittest.mock import patch

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

        # La vue importe `part.models.Part` à l'exécution — on le mocke pour
        # ne pas dépendre des données InvenTree dans ce test ciblé sur l'auth.
        with patch("part.models.Part") as part_mock:
            part_mock.objects.count.return_value = 0
            response = ExampleView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert "random_text" in response.data
        assert response.data["part_count"] == 0


class TestPermissionClassesAreSet:
    def test_example_view_requires_authentication(self):
        from rest_framework.permissions import IsAuthenticated

        assert IsAuthenticated in ExampleView.permission_classes
