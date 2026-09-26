"""Composition du tableau de bord InvenTree à partir des rôles du plugin."""

from __future__ import annotations

from . import roles

#: Slug du plugin tel qu'InvenTree le préfixe aux identifiants de widget.
PLUGIN_SLUG = "inventree-location"

#: Gabarit de chaque widget, dans l'ordre où on veut les empiler sur le tableau
#: de bord.
WIDGET_SIZES: dict[str, tuple[int, int]] = {
    # Le poste tient lieu de page : pleine largeur, en tête.
    "inventree-location-poste": (12, 10),
    "inventree-location-catalog": (12, 8),
    "inventree-location-organisation": (12, 8),
    "inventree-location-reservations": (12, 8),
    "inventree-location-calendrier": (12, 8),
    "inventree-location-ramassages": (12, 8),
    "inventree-location-deliveries": (12, 8),
    "inventree-location-conflicts": (12, 8),
    "inventree-location-stock-alerts": (12, 6),
    "inventree-location-backoffice-users": (12, 8),
    "inventree-location-backoffice-parts": (12, 8),
}

#: Points de rupture qu'InvenTree enregistre (relevé sur une disposition réelle).
BREAKPOINTS: tuple[str, ...] = ("lg", "sm")


def widget_dom_id(key: str) -> str:
    """Identifiant du widget côté interface : `p-<slug plugin>-<clé widget>`."""

    return f"p-{PLUGIN_SLUG}-{key}"


def widget_key(dom_id: str) -> str | None:
    """Clé de widget correspondant à un identifiant, ou None s'il est étranger."""

    prefix = f"p-{PLUGIN_SLUG}-"

    if not dom_id.startswith(prefix):
        return None

    return dom_id[len(prefix) :]


def is_plugin_widget(dom_id: str) -> bool:
    """Vrai si l'identifiant désigne un widget de ce plugin."""

    return widget_key(dom_id) is not None


def _layout_entry(key: str, y: int) -> dict:
    width, height = WIDGET_SIZES[key]

    return {
        "i": widget_dom_id(key),
        "x": 0,
        "y": y,
        "w": width,
        "h": height,
        "minW": width,
        "minH": height,
    }


def _ordered(keys) -> list[str]:
    """Clés connues, dans l'ordre d'affichage, sans doublon."""

    wanted = set(keys)

    return [key for key in WIDGET_SIZES if key in wanted]


def build_dashboard_state(widget_keys) -> dict:
    """Disposition complète pour un tableau de bord vierge."""

    entries: list[dict] = []
    y = 0

    for key in _ordered(widget_keys):
        entries.append(_layout_entry(key, y))
        y += WIDGET_SIZES[key][1]

    return {
        "layouts": {
            breakpoint_: [dict(entry) for entry in entries]
            for breakpoint_ in BREAKPOINTS
        },
        "widgets": [entry["i"] for entry in entries],
    }


def _existing_layouts(current) -> dict[str, list[dict]]:
    """Layouts exploitables d'un état existant, quelle qu'en soit la forme."""

    if not isinstance(current, dict):
        return {}

    layouts = current.get("layouts")

    if not isinstance(layouts, dict):
        return {}

    cleaned: dict[str, list[dict]] = {}

    for breakpoint_, entries in layouts.items():
        if not isinstance(entries, list):
            continue

        cleaned[breakpoint_] = [
            entry
            for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("i"), str)
        ]

    return cleaned


def merge_dashboard_state(current, allowed_keys) -> dict:
    """Met l'état existant en cohérence avec les widgets autorisés."""

    allowed = set(_ordered(allowed_keys))
    layouts = _existing_layouts(current)
    breakpoints = tuple(layouts) or BREAKPOINTS

    merged: dict[str, list[dict]] = {}

    for breakpoint_ in breakpoints:
        kept = [
            entry
            for entry in layouts.get(breakpoint_, [])
            if not is_plugin_widget(entry["i"]) or widget_key(entry["i"]) in allowed
        ]

        present = {
            widget_key(entry["i"]) for entry in kept if is_plugin_widget(entry["i"])
        }

        y = max((entry.get("y", 0) + entry.get("h", 0) for entry in kept), default=0)

        for key in _ordered(allowed - present):
            kept.append(_layout_entry(key, y))
            y += WIDGET_SIZES[key][1]

        merged[breakpoint_] = kept

    reference = merged.get(BREAKPOINTS[0]) or next(iter(merged.values()), [])

    return {
        "layouts": merged,
        "widgets": [entry["i"] for entry in reference],
    }


def dashboard_state_for_user(user, current=None) -> dict:
    """Disposition attendue pour cet utilisateur, d'après ses rôles."""

    return merge_dashboard_state(current, roles.visible_dashboard_widget_keys(user))
