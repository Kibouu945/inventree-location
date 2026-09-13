"""Composition du tableau de bord InvenTree à partir des rôles du plugin.

InvenTree ouvre un tableau de bord **vide** : les widgets d'un plugin n'y
figurent que si l'utilisateur va les chercher un par un dans « Add Widget ».
Le client a testé l'instance en ligne et en a conclu qu'il avait « la version de
base d'InvenTree » — rien de ce qui a été développé n'était visible. On pose
donc les écrans nous-mêmes dès qu'un rôle est attribué.

La disposition vit côté serveur, dans `users.models.UserProfile.widgets`, au
format que produit react-grid-layout :

    {"layouts": {"lg": [{"i": ..., "x": 0, "y": 0, "w": 12, "h": 8,
                         "minW": 12, "minH": 8}, ...], "sm": [...]},
     "widgets": ["p-inventree-location-inventree-location-catalog", ...]}

Ce module ne contient que le calcul pur — aucun accès base, aucun import
InvenTree — pour rester testable hors de la stack, comme `roles` et
`conflicts` (`core` n'est pas importable en pytest).
"""

from __future__ import annotations

from . import roles

#: Slug du plugin tel qu'InvenTree le préfixe aux identifiants de widget.
PLUGIN_SLUG = "inventree-location"

#: Gabarit de chaque widget, dans l'ordre où on veut les empiler sur le
#: tableau de bord. Les valeurs doublent les `options` de
#: `core.get_ui_dashboard_items` : InvenTree ne les applique qu'à l'ajout
#: manuel, on les reproduit donc ici pour une pose automatique identique.
WIDGET_SIZES: dict[str, tuple[int, int]] = {
    # Le poste tient lieu de page : pleine largeur, en tête. La hauteur est un
    # compromis — la boîte est exprimée en lignes de grille et ne sait rien de
    # la fenêtre (cf. `postes/Poste.tsx`).
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
    """Clés connues, dans l'ordre d'affichage, sans doublon.

    `WIDGET_SIZES` fait foi pour l'ordre : une clé absente est ignorée plutôt
    que posée sans gabarit (elle sortirait en boîte minuscule, illisible).
    """

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
    """Layouts exploitables d'un état existant, quelle qu'en soit la forme.

    Le champ est un JSON libre, nullable, écrit par le navigateur : on ne peut
    pas supposer qu'il est bien formé. Tout ce qui n'est pas une liste de
    dictionnaires est traité comme absent plutôt que de faire échouer la pose.
    """

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
    """Met l'état existant en cohérence avec les widgets autorisés.

    Non destructif, parce qu'un changement de rôle ne doit pas effacer un
    tableau de bord que l'utilisateur a rangé lui-même :

    - les widgets du cœur d'InvenTree ne sont jamais touchés ;
    - les widgets du plugin devenus interdits sont retirés ;
    - les widgets nouvellement autorisés sont ajoutés **sous** l'existant ;
    - l'ordre et les tailles déjà en place sont conservés.
    """

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
