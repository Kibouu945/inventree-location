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


def _avec_role(username, role):
    """Crée un compte actif portant un rôle du plugin."""

    from django.contrib.auth.models import Group

    compte = User.objects.create_user(username=username, password="pwd12345")
    compte.groups.add(Group.objects.get(name=role))

    return compte


@pytest.mark.django_db
class TestUserListRoleFilters:
    """Filtres de rôle du sélecteur d'utilisateurs.

    Revue interne du 07/09/2026 : « dans le champ gérant interne, ne pas
    afficher le client (l'organisateur) ». Le sélecteur servait la même liste
    à tout le monde, on pouvait donc désigner un client comme responsable
    interne de sa propre réservation. Le CDC V06 sépare pourtant les deux
    rôles — l'organisateur commande et signe les devis (persona 1), le
    gestionnaire traite (persona 2) — et sa matrice RACI n'a même pas de
    colonne « organisateur ».
    """

    def _usernames(self, factory, user, params):
        request = factory.get(USERS_URL, params)
        force_authenticate(request, user=user)
        response = UserListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK

        return {row["username"] for row in response.data["results"]}

    def test_exclude_roles_ecarte_les_organisateurs(self, factory, user):
        from inventree_location import roles

        _avec_role("client-dupont", roles.ORGANISATEUR)
        _avec_role("magasin", roles.MAGASINIER)

        noms = self._usernames(
            factory, user, {"exclude_roles": roles.ORGANISATEUR}
        )

        assert "client-dupont" not in noms
        assert {"alice", "magasin"} <= noms

    def test_roles_ne_garde_que_les_roles_demandes(self, factory, user):
        from inventree_location import roles

        _avec_role("client-dupont", roles.ORGANISATEUR)
        _avec_role("magasin", roles.MAGASINIER)

        noms = self._usernames(
            factory, user, {"roles": f"{roles.MAGASINIER},{roles.LIVREUR}"}
        )

        assert noms == {"magasin"}

    def test_un_compte_a_deux_roles_nest_rendu_quune_fois(self, factory, user):
        from django.contrib.auth.models import Group

        from inventree_location import roles

        cumul = _avec_role("polyvalent", roles.MAGASINIER)
        cumul.groups.add(Group.objects.get(name=roles.LIVREUR))

        request = factory.get(
            USERS_URL, {"roles": f"{roles.MAGASINIER},{roles.LIVREUR}"}
        )
        force_authenticate(request, user=user)
        response = UserListView.as_view()(request)

        usernames = [row["username"] for row in response.data["results"]]

        assert usernames.count("polyvalent") == 1

    def test_un_role_inconnu_est_ignore_plutot_que_refuse(self, factory, user):
        # Un nom de rôle qui n'existe pas est du bruit, pas une erreur : un 400
        # sur un sélecteur d'interface serait pire que de l'ignorer.
        noms = self._usernames(factory, user, {"exclude_roles": "cuisinier"})

        assert "alice" in noms

    def test_sans_parametre_la_liste_est_inchangee(self, factory, user):
        from inventree_location import roles

        _avec_role("client-dupont", roles.ORGANISATEUR)

        noms = self._usernames(factory, user, {})

        assert {"alice", "client-dupont"} <= noms
