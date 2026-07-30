"""Rôles et personas du plugin (TR-03).

Les rôles sont matérialisés par des groupes Django (`auth.Group`).
Ce module centralise les noms de rôles et les helpers de lecture.

Personas du CDC :
- admin         : CRUD complet + configuration du plugin
- gestionnaire  : manifestations / prestations / réservations + arbitrage conflits
- magasinier    : check-in retours + stock
- livreur       : tournées + statuts livraison / ramassage + Maps
- sav           : tickets réparation + historique
- organisateur  : ses manifestations / réservations
- lecteur       : lecture seule événement / stock
- acheteur      : achats / besoins matériel
"""

from __future__ import annotations

ADMIN = "admin"
GESTIONNAIRE = "gestionnaire"
MAGASINIER = "magasinier"
LIVREUR = "livreur"
SAV = "sav"
ORGANISATEUR = "organisateur"
LECTEUR = "lecteur"
ACHETEUR = "acheteur"

ALL_ROLES: tuple[str, ...] = (
    ADMIN,
    GESTIONNAIRE,
    MAGASINIER,
    LIVREUR,
    SAV,
    ORGANISATEUR,
    LECTEUR,
    ACHETEUR,
)


def user_roles(user) -> set[str]:
    """Retourne l'ensemble des rôles plugin de l'utilisateur."""

    if not user or not user.is_authenticated:
        return set()

    return set(user.groups.values_list("name", flat=True)) & set(ALL_ROLES)


def user_has_any_role(user, roles) -> bool:
    """Vrai si l'utilisateur possède au moins un des rôles fournis.

    Un superutilisateur est toujours considéré comme autorisé.
    """

    if user and getattr(user, "is_superuser", False):
        return True

    return bool(user_roles(user) & set(roles))


DASHBOARD_WIDGET_ROLES: dict[str, set[str]] = {
    "inventree-location-catalog": {
        ADMIN,
        GESTIONNAIRE,
        MAGASINIER,
        LECTEUR,
        ACHETEUR,
    },
    "inventree-location-reservations": {
        ADMIN,
        GESTIONNAIRE,
        MAGASINIER,
        LIVREUR,
        ORGANISATEUR,
        LECTEUR,
    },
    "inventree-location-ramassages": {
        ADMIN,
        GESTIONNAIRE,
        MAGASINIER,
        LIVREUR,
    },
    "inventree-location-conflicts": {
        ADMIN,
        GESTIONNAIRE,
        LECTEUR,
    },
    "inventree-location-backoffice-users": {
        ADMIN,
    },
    "inventree-location-backoffice-parts": {
        ADMIN,
    },
}


def visible_dashboard_widget_keys(user) -> set[str]:
    """Clés des widgets dashboard visibles pour cet utilisateur."""

    if not user_has_any_role(user, ALL_ROLES):
        return set()

    if getattr(user, "is_superuser", False):
        return set(DASHBOARD_WIDGET_ROLES)

    owned = user_roles(user)

    return {
        key
        for key, allowed in DASHBOARD_WIDGET_ROLES.items()
        if owned & allowed
    }