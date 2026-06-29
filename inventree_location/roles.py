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
