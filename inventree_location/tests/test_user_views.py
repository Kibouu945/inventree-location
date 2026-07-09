"""Tests de `UserListView` : lecture seule, recherche, utilisateurs actifs uniquement."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location.views import UserListView

User = get_user_model()

USERS_URL = "/plugin/inventree-location/users/"


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def user(db):
    from django.contrib.auth.models import Group

    from inventree_location import roles

    account = User.objects.create_user(
        username="alice", password="pwd12345", first_name="Alice", last_name="Martin"
    )
    account.groups.add(Group.objects.get(name=roles.GESTIONNAIRE))
    return account


class TestUserListView:
    def test_anonymous_returns_401(self, factory):
        request = factory.get(USERS_URL)
        response = UserListView.as_view()(request)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_list_returns_active_users(self, factory, user):
        User.objects.create_user(username="inactive", is_active=False)

        request = factory.get(USERS_URL)
        force_authenticate(request, user=user)
        response = UserListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        usernames = {row["username"] for row in response.data["results"]}
        assert usernames == {"alice"}

    @pytest.mark.django_db
    def test_search_by_last_name(self, factory, user):
        request = factory.get(USERS_URL, {"search": "martin"})
        force_authenticate(request, user=user)
        response = UserListView.as_view()(request)
        assert len(response.data["results"]) == 1

        request = factory.get(USERS_URL, {"search": "introuvable"})
        force_authenticate(request, user=user)
        response = UserListView.as_view()(request)
        assert len(response.data["results"]) == 0
