"""Rôles et personas du plugin (TR-03)."""

from __future__ import annotations

ADMIN = "admin"
GESTIONNAIRE = "gestionnaire"
MAGASINIER = "magasinier"
LIVREUR = "livreur"
SAV = "sav"
LECTEUR = "lecteur"
ACHETEUR = "acheteur"

ALL_ROLES: tuple[str, ...] = (
    ADMIN,
    GESTIONNAIRE,
    MAGASINIER,
    LIVREUR,
    SAV,
    LECTEUR,
    ACHETEUR,
)


#: Rulesets InvenTree ouverts en écriture (ajout + modification) par rôle.
ROLE_WRITE_RULESETS: dict[str, frozenset[str]] = {
    ADMIN: frozenset({
        "part_category",
        "part",
        "bom",
        "stock_location",
        "stock",
        "purchase_order",
    }),
    GESTIONNAIRE: frozenset({"part_category", "part", "stock_location", "stock"}),
    MAGASINIER: frozenset({"part_category", "part", "stock_location", "stock"}),
    ACHETEUR: frozenset({"purchase_order"}),
    LIVREUR: frozenset(),
    SAV: frozenset(),
    LECTEUR: frozenset(),
}


#: Rulesets InvenTree **visibles** par rôle — et donc entrées de la barre de
#: navigation native : ses onglets sont conditionnés à `hasViewRole(...)`
ROLE_VIEW_RULESETS: dict[str, frozenset[str]] = {
    ADMIN: frozenset({
        "admin",
        "bom",
        "build",
        "part",
        "part_category",
        "purchase_order",
        "return_order",
        "sales_order",
        "stock",
        "stock_location",
        "transfer_order",
    }),
    GESTIONNAIRE: frozenset({
        "bom",
        "part",
        "part_category",
        "stock",
        "stock_location",
    }),
    MAGASINIER: frozenset({
        "bom",
        "part",
        "part_category",
        "stock",
        "stock_location",
        "transfer_order",
    }),
    ACHETEUR: frozenset({
        "bom",
        "part",
        "part_category",
        "purchase_order",
        "stock",
        "stock_location",
    }),
    SAV: frozenset({
        "bom",
        "part",
        "part_category",
        "stock",
        "stock_location",
    }),
    LECTEUR: frozenset({
        "bom",
        "part",
        "part_category",
        "stock",
        "stock_location",
    }),
    # Le livreur : tout vient des endpoints du plugin, sa barre se réduit au
    # Dashboard.
    LIVREUR: frozenset(),
}


#: Seule exception à « on désactive, on ne supprime pas » (SCRUM-111) : une
#: ligne de nomenclature n'a pas d'état inactif, un pack mal composé se
#: corrige en retirant l'élément.
ROLE_DELETE_RULESETS: dict[str, frozenset[str]] = {
    ADMIN: frozenset({"bom"}),
}


def ruleset_permissions(role: str, ruleset: str) -> dict[str, bool]:
    """Droits attendus pour ce rôle sur ce ruleset InvenTree."""

    writable = ruleset in ROLE_WRITE_RULESETS.get(role, frozenset())
    viewable = ruleset in ROLE_VIEW_RULESETS.get(role, frozenset())
    deletable = ruleset in ROLE_DELETE_RULESETS.get(role, frozenset())

    return {
        "can_view": viewable or writable,
        "can_add": writable,
        "can_change": writable,
        "can_delete": deletable,
    }


def user_roles(user) -> set[str]:
    """Rôles plugin de l'utilisateur."""

    if not user or not user.is_authenticated:
        return set()

    return set(user.groups.values_list("name", flat=True)) & set(ALL_ROLES)


def user_has_any_role(user, roles) -> bool:
    """Vrai si l'utilisateur possède au moins un des rôles fournis."""

    if user and getattr(user, "is_superuser", False):
        return True

    return bool(user_roles(user) & set(roles))


def sees_only_deliverable_reservations(user) -> bool:
    """Vrai pour un livreur : il ne voit que les réservations validées."""

    if getattr(user, "is_superuser", False):
        return False

    return LIVREUR in user_roles(user)


#: Rôles habilités à arbitrer une réservation (valider / refuser).
ARBITRAGE_ROLES: tuple[str, ...] = (ADMIN, GESTIONNAIRE)


def can_arbitrate_reservations(user) -> bool:
    """Vrai si l'utilisateur peut valider / refuser une réservation."""

    return user_has_any_role(user, ARBITRAGE_ROLES)


#: Widgets dashboard visibles par rôle métier (RBAC, cf. cahier des charges —
#: un filtrage sur les 7 groupes, PAS sur ``is_staff``).
DASHBOARD_WIDGET_ROLES: dict[str, set[str]] = {
    # Un seul widget : le poste de travail du rôle, qui porte les écrans métier
    # dans sa propre navigation.
    "inventree-location-poste": {
        ADMIN,
        GESTIONNAIRE,
        MAGASINIER,
        LIVREUR,
        ACHETEUR,
        LECTEUR,
    },
    # Les widgets historiques restent déclarés mais ne sont plus attribués :
    # leur contenu vit dans les postes. À supprimer après la recette.
}


def visible_dashboard_widget_keys(user) -> set[str]:
    """Clés des widgets dashboard visibles pour cet utilisateur."""

    if not user_has_any_role(user, ALL_ROLES):
        return set()

    if getattr(user, "is_superuser", False):
        return set(DASHBOARD_WIDGET_ROLES)

    owned = user_roles(user)

    return {key for key, allowed in DASHBOARD_WIDGET_ROLES.items() if owned & allowed}
