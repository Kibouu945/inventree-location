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
ORGANISATION = "inventree-location-organisation"
STOCK_ALERTS = "inventree-location-stock-alerts"
DELIVERIES = "inventree-location-deliveries"
RAMASSAGES = "inventree-location-ramassages"
BACKOFFICE_USERS = "inventree-location-backoffice-users"
BACKOFFICE_PARTS = "inventree-location-backoffice-parts"

#: Dérivé du mapping et non figé en dur : un widget ajouté à
#: ``DASHBOARD_WIDGET_ROLES`` sans toucher ce test faisait échouer cinq cas d'un
#: coup, sans que la régression concerne les rôles.
ALL_WIDGETS = set(roles.DASHBOARD_WIDGET_ROLES)
#: Back-offices : administrateur seulement.
BACKOFFICE_WIDGETS = {BACKOFFICE_USERS, BACKOFFICE_PARTS}
#: Le gestionnaire voit tout le métier, mais pas les back-offices.
GESTIONNAIRE_WIDGETS = ALL_WIDGETS - BACKOFFICE_WIDGETS
#: Le lecteur ne voit pas non plus les écrans d'exécution terrain.
LECTEUR_WIDGETS = GESTIONNAIRE_WIDGETS - {DELIVERIES, RAMASSAGES}


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
            (roles.GESTIONNAIRE, GESTIONNAIRE_WIDGETS),
            (roles.LECTEUR, LECTEUR_WIDGETS),
            # Le magasinier suit la disponibilité future et l'inventaire :
            # les alertes de seuil le concernent (US-09).
            (roles.MAGASINIER, {CATALOG, RESERVATIONS, STOCK_ALERTS, RAMASSAGES}),
            (roles.ORGANISATEUR, {RESERVATIONS, ORGANISATION}),
            (roles.LIVREUR, {RESERVATIONS, DELIVERIES, RAMASSAGES}),
            (roles.SAV, set()),
            # L'acheteur consulte le catalogue pour ses achats, rien de plus.
            (roles.ACHETEUR, {CATALOG}),
        ],
    )
    def test_widgets_per_role(self, role, expected):
        user = _make_user(f"user_{role}", role=role)

        assert roles.visible_dashboard_widget_keys(user) == expected

    def test_livreur_sees_reservations_and_deliveries_but_not_conflicts(self):
        user = _make_user("livreur1", role=roles.LIVREUR)

        keys = roles.visible_dashboard_widget_keys(user)

        assert RESERVATIONS in keys
        assert DELIVERIES in keys
        assert CONFLICTS not in keys
        assert CATALOG not in keys
