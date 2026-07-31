"""Rôles et personas du plugin (TR-03).

Les rôles sont matérialisés par des groupes Django (`auth.Group`) créés via
migration. Ce module centralise les noms de rôles et les helpers de lecture,
afin que les permissions DRF (cf. `permissions.py`) et les tests partagent une
source unique de vérité.

Personas confirmés (réunion Tassin du 21 mai) :
- admin        : CRUD complet + configuration du plugin
- gestionnaire : manifestations / prestations / réservations + arbitrage conflits
- magasinier   : check-in retours + stock
- livreur      : tournées + statuts livraison / ramassage + Maps
- sav          : tickets réparation + historique 90 j
- organisateur : ses manifestations / réservations
- lecteur      : lecture seule
"""

from __future__ import annotations

ADMIN = "admin"
GESTIONNAIRE = "gestionnaire"
MAGASINIER = "magasinier"
LIVREUR = "livreur"
SAV = "sav"
ORGANISATEUR = "organisateur"
LECTEUR = "lecteur"

#: Liste ordonnée des 7 rôles (sert à la création des groupes en migration).
ALL_ROLES: tuple[str, ...] = (
    ADMIN,
    GESTIONNAIRE,
    MAGASINIER,
    LIVREUR,
    SAV,
    ORGANISATEUR,
    LECTEUR,
)


def user_roles(user) -> set[str]:
    """Retourne l'ensemble des rôles (noms de groupes connus) de l'utilisateur."""

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


#: Rôles voyant les réservations tous statuts confondus.
FULL_RESERVATION_VIEW_ROLES: tuple[str, ...] = (
    ADMIN,
    GESTIONNAIRE,
    ORGANISATEUR,
    MAGASINIER,
    SAV,
    LECTEUR,
)


def sees_only_deliverable_reservations(user) -> bool:
    """Vrai pour un livreur pur : il ne voit que les réservations validées."""

    if getattr(user, "is_superuser", False):
        return False

    owned = user_roles(user)

    return LIVREUR in owned and not (owned & set(FULL_RESERVATION_VIEW_ROLES))


#: Rôles habilités à arbitrer une réservation (valider / refuser).
ARBITRAGE_ROLES: tuple[str, ...] = (ADMIN, GESTIONNAIRE)


def can_arbitrate_reservations(user) -> bool:
    """Vrai si l'utilisateur peut valider / refuser une réservation."""

    return user_has_any_role(user, ARBITRAGE_ROLES)


#: Widgets dashboard visibles par rôle métier (RBAC, cf. cahier des charges —
#: un filtrage sur les 7 groupes, PAS sur ``is_staff``). Les écrans propres à
#: certains rôles (tournées livreur, retours magasinier, tickets SAV) arriveront
#: aux sprints suivants ; on ne mappe ici que les widgets existants.
DASHBOARD_WIDGET_ROLES: dict[str, set[str]] = {
    "inventree-location-organisation": {ADMIN, GESTIONNAIRE, ORGANISATEUR, LECTEUR},
    "inventree-location-catalog": {ADMIN, GESTIONNAIRE, MAGASINIER, LECTEUR},
    "inventree-location-reservations": {
        ADMIN,
        GESTIONNAIRE,
        MAGASINIER,
        LIVREUR,
        ORGANISATEUR,
        LECTEUR,
    },
    "inventree-location-conflicts": {ADMIN, GESTIONNAIRE, LECTEUR},
}


def visible_dashboard_widget_keys(user) -> set[str]:
    """Clés des widgets dashboard visibles pour cet utilisateur (RBAC métier).

    - un utilisateur sans rôle plugin ne voit rien ;
    - le superutilisateur voit tous les widgets ;
    - sinon, chaque widget est visible si l'un des rôles de l'utilisateur
      figure dans ``DASHBOARD_WIDGET_ROLES``.
    """

    if not user_has_any_role(user, ALL_ROLES):
        return set()

    if getattr(user, "is_superuser", False):
        return set(DASHBOARD_WIDGET_ROLES)

    owned = user_roles(user)

    return {key for key, allowed in DASHBOARD_WIDGET_ROLES.items() if owned & allowed}
