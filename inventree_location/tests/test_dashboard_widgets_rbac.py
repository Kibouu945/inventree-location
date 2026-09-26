"""RBAC des widgets dashboard : visibilité pilotée par les 7 groupes métier."""

from __future__ import annotations

import pytest

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group

from inventree_location import roles

User = get_user_model()

POSTE = "inventree-location-poste"

#: Dérivé du mapping et non figé en dur : un widget ajouté à
#: ``DASHBOARD_WIDGET_ROLES`` sans toucher ce test faisait échouer cinq cas
ALL_WIDGETS = set(roles.DASHBOARD_WIDGET_ROLES)

#: Rôles disposant d'un poste de travail. Les écrans métier ne sont plus des
#: widgets : ils vivent dans la navigation du poste.
ROLES_AVEC_POSTE = (
    roles.ADMIN,
    roles.GESTIONNAIRE,
    roles.MAGASINIER,
    roles.LIVREUR,
    roles.ACHETEUR,
    roles.LECTEUR,
)

#: ``sav`` attend la refonte du bloc retours pour avoir son poste.
ROLES_SANS_POSTE = (roles.SAV,)


def _make_user(username, role=None, *, is_staff=False, is_superuser=False):
    user = User.objects.create_user(
        username=username,
        password="pwd12345",
        is_staff=is_staff,
        is_superuser=is_superuser,
    )

    if role is not None:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)

    return user


@pytest.mark.django_db
class TestVisibleDashboardWidgetKeys:
    def test_anonymous_sees_nothing(self):
        assert roles.visible_dashboard_widget_keys(AnonymousUser()) == set()

    def test_none_user_sees_nothing(self):
        assert roles.visible_dashboard_widget_keys(None) == set()

    def test_authenticated_without_plugin_role_sees_nothing(self):
        # Même staff : sans rôle plugin, aucun widget (on ne filtre pas sur is_staff).
        user = _make_user("random_staff", role=None, is_staff=True)

        assert roles.visible_dashboard_widget_keys(user) == set()

    def test_superuser_sees_all_widgets(self):
        user = _make_user("root", role=None, is_superuser=True)

        assert roles.visible_dashboard_widget_keys(user) == ALL_WIDGETS

    @pytest.mark.parametrize("role", ROLES_AVEC_POSTE)
    def test_un_role_metier_voit_le_widget_de_poste(self, role):
        user = _make_user(f"user_{role}", role=role)

        assert roles.visible_dashboard_widget_keys(user) == {POSTE}

    @pytest.mark.parametrize("role", ROLES_SANS_POSTE)
    def test_un_role_sans_poste_ne_voit_rien(self, role):
        user = _make_user(f"user_{role}", role=role)

        assert roles.visible_dashboard_widget_keys(user) == set()

    def test_plus_aucun_ecran_metier_n_est_un_widget(self):
        # Échoue si quelqu'un réattribue un ancien widget à un rôle au lieu
        # d'en faire une entrée de poste.
        assert set(roles.DASHBOARD_WIDGET_ROLES) == {POSTE}
