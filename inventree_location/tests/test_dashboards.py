"""Composition automatique du tableau de bord à partir des rôles."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group

from inventree_location import dashboards, roles

User = get_user_model()

CATALOG = "inventree-location-catalog"
ORGANISATION = "inventree-location-organisation"
RESERVATIONS = "inventree-location-reservations"
STOCK_ALERTS = "inventree-location-stock-alerts"
BACKOFFICE_USERS = "inventree-location-backoffice-users"

CORE_WIDGET = "part-count-widget"


def dom(key: str) -> str:
    return dashboards.widget_dom_id(key)


def test_every_widget_of_the_rbac_mapping_has_a_size():
    """Un widget attribué à un rôle sans gabarit ici sortirait en boîte minuscule."""

    assert set(roles.DASHBOARD_WIDGET_ROLES) <= set(dashboards.WIDGET_SIZES)


def test_dom_id_round_trip():
    assert dom(CATALOG) == "p-inventree-location-inventree-location-catalog"
    assert dashboards.widget_key(dom(CATALOG)) == CATALOG


def test_a_foreign_widget_is_not_recognised_as_ours():
    assert dashboards.widget_key(CORE_WIDGET) is None
    assert not dashboards.is_plugin_widget(CORE_WIDGET)


def test_build_stacks_widgets_in_declaration_order():
    state = dashboards.build_dashboard_state({RESERVATIONS, CATALOG})

    assert state["widgets"] == [dom(CATALOG), dom(RESERVATIONS)]


def test_build_gives_each_widget_its_declared_size_and_stacks_them():
    state = dashboards.build_dashboard_state({CATALOG, STOCK_ALERTS})
    entries = state["layouts"]["lg"]

    assert [(e["w"], e["h"]) for e in entries] == [(12, 8), (12, 6)]
    # Empilés sans chevauchement : le second commence là où le premier finit.
    assert [(e["x"], e["y"]) for e in entries] == [(0, 0), (0, 8)]


def test_build_repeats_the_layout_on_every_breakpoint():
    state = dashboards.build_dashboard_state({CATALOG})

    assert set(state["layouts"]) == set(dashboards.BREAKPOINTS)
    assert state["layouts"]["lg"] == state["layouts"]["sm"]


def test_build_ignores_an_unknown_widget_rather_than_placing_it_blind():
    state = dashboards.build_dashboard_state({CATALOG, "widget-inexistant"})

    assert state["widgets"] == [dom(CATALOG)]


@pytest.mark.parametrize("current", [None, {}, {"layouts": "cassé"}, "n'importe quoi"])
def test_merge_treats_an_unusable_state_as_empty(current):
    """Le champ est un JSON libre écrit par le navigateur : jamais de confiance."""

    state = dashboards.merge_dashboard_state(current, {CATALOG})

    assert state["widgets"] == [dom(CATALOG)]


def test_merge_keeps_core_inventree_widgets_untouched():
    current = {
        "layouts": {"lg": [{"i": CORE_WIDGET, "x": 0, "y": 0, "w": 4, "h": 3}]},
        "widgets": [CORE_WIDGET],
    }

    state = dashboards.merge_dashboard_state(current, {CATALOG})

    assert CORE_WIDGET in state["widgets"]
    assert state["layouts"]["lg"][0] == current["layouts"]["lg"][0]


def test_merge_appends_new_widgets_below_what_is_already_there():
    current = {
        "layouts": {"lg": [{"i": CORE_WIDGET, "x": 0, "y": 0, "w": 4, "h": 3}]},
        "widgets": [CORE_WIDGET],
    }

    state = dashboards.merge_dashboard_state(current, {CATALOG})
    added = state["layouts"]["lg"][1]

    assert added["i"] == dom(CATALOG)
    assert added["y"] == 3


def test_merge_removes_a_plugin_widget_that_is_no_longer_allowed():
    current = dashboards.build_dashboard_state({CATALOG, BACKOFFICE_USERS})

    state = dashboards.merge_dashboard_state(current, {CATALOG})

    assert state["widgets"] == [dom(CATALOG)]


def test_merge_preserves_a_layout_the_user_arranged_himself():
    """Un changement de rôle ne doit pas défaire le rangement de l'utilisateur."""

    current = {
        "layouts": {
            "lg": [{"i": dom(CATALOG), "x": 6, "y": 4, "w": 6, "h": 5}],
        },
        "widgets": [dom(CATALOG)],
    }

    state = dashboards.merge_dashboard_state(current, {CATALOG})

    assert state["layouts"]["lg"][0] == current["layouts"]["lg"][0]


def test_merge_is_idempotent():
    first = dashboards.merge_dashboard_state(None, {CATALOG, RESERVATIONS})
    second = dashboards.merge_dashboard_state(first, {CATALOG, RESERVATIONS})

    assert second == first


def test_merge_applies_to_every_breakpoint_already_stored():
    current = {
        "layouts": {
            "lg": [{"i": CORE_WIDGET, "x": 0, "y": 0, "w": 4, "h": 3}],
            "xs": [{"i": CORE_WIDGET, "x": 0, "y": 0, "w": 2, "h": 3}],
        },
        "widgets": [CORE_WIDGET],
    }

    state = dashboards.merge_dashboard_state(current, {CATALOG})

    assert set(state["layouts"]) == {"lg", "xs"}
    for entries in state["layouts"].values():
        assert dom(CATALOG) in [entry["i"] for entry in entries]


@pytest.mark.django_db
def test_state_for_a_role_holder_follows_the_rbac_mapping():
    user = User.objects.create_user(username="gestion", password="x")
    # Les groupes de rôles sont posés par migration : get_or_create, pas create.
    group, _ = Group.objects.get_or_create(name=roles.GESTIONNAIRE)
    user.groups.add(group)

    state = dashboards.dashboard_state_for_user(user)
    keys = {dashboards.widget_key(i) for i in state["widgets"]}

    assert keys == roles.visible_dashboard_widget_keys(user)
    assert BACKOFFICE_USERS not in keys


@pytest.mark.django_db
def test_a_user_without_any_role_gets_nothing():
    user = User.objects.create_user(username="sansrole", password="x")

    assert dashboards.dashboard_state_for_user(user)["widgets"] == []


def test_an_anonymous_visitor_gets_nothing():
    assert dashboards.dashboard_state_for_user(AnonymousUser())["widgets"] == []
