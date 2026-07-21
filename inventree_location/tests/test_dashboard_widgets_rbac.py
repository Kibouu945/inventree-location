"""RBAC des widgets dashboard : visibilité pilotée par les 7 groupes métier.

Vérifie ``roles.visible_dashboard_widget_keys`` — la logique extraite de
``core.get_ui_dashboard_items`` (``core`` n'est pas importable hors InvenTree,
d'où le test sur le helper pur). Le filtrage doit reposer sur les rôles, PAS
sur ``is_staff`` (cf. cahier des charges).
"""

from __future__ import annotations

import pytest

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group

from inventree_location import roles

User = get_user_model()

CATALOG = "inventree-location-catalog"
RESERVATIONS = "inventree-location-reservations"
CONFLICTS = "inventree-location-conflicts"
ALL_WIDGETS = {CATALOG, RESERVATIONS, CONFLICTS}


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

    @pytest.mark.parametrize(
        "role, expected",
        [
            (roles.ADMIN, ALL_WIDGETS),
            (roles.GESTIONNAIRE, ALL_WIDGETS),
            (roles.LECTEUR, ALL_WIDGETS),
            (roles.MAGASINIER, {CATALOG, RESERVATIONS}),
            (roles.ORGANISATEUR, {RESERVATIONS}),
            (roles.LIVREUR, {RESERVATIONS}),
            (roles.SAV, set()),
        ],
    )
    def test_widgets_per_role(self, role, expected):
        user = _make_user(f"user_{role}", role=role)

        assert roles.visible_dashboard_widget_keys(user) == expected

    def test_livreur_sees_reservations_but_not_conflicts(self):
        user = _make_user("livreur1", role=roles.LIVREUR)

        keys = roles.visible_dashboard_widget_keys(user)

        assert RESERVATIONS in keys
        assert CONFLICTS not in keys
        assert CATALOG not in keys
