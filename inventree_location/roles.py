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


#: Rulesets InvenTree ouverts en écriture (ajout + modification) par rôle.
#:
#: Les groupes du plugin ne portaient aucun droit InvenTree : les écrans
#: natifs étaient donc réglés à la main dans l'admin, sans trace dans le code.
#: Un compte sans droit d'écriture sur un ruleset ne voit même pas le bouton
#: de création — c'est ce qui empêchait le client d'enregistrer un fournisseur
#: (`company_company` relève du ruleset `purchase_order`, cf. CDC V06
#: § « Achat fournisseur » et sa matrice RACI, qui confie les fiches
#: fournisseurs et les achats à l'acheteur).
#:
#: Tout ruleset absent de cette table reste en **lecture seule** : une version
#: future d'InvenTree qui en ajoute un n'ouvre donc rien par surprise. La
#: suppression n'est jamais accordée — le back-office désactive (`active`), il
#: ne supprime pas (SCRUM-111).
ROLE_WRITE_RULESETS: dict[str, frozenset[str]] = {
    ADMIN: frozenset({
        "part_category",
        "part",
        "stock_location",
        "stock",
        "purchase_order",
    }),
    GESTIONNAIRE: frozenset({"part_category", "part", "stock_location", "stock"}),
    MAGASINIER: frozenset({"part_category", "part", "stock_location", "stock"}),
    ACHETEUR: frozenset({"purchase_order"}),
    LIVREUR: frozenset(),
    SAV: frozenset(),
    ORGANISATEUR: frozenset(),
    LECTEUR: frozenset(),
}


def ruleset_permissions(role: str, ruleset: str) -> dict[str, bool]:
    """Droits attendus pour ce rôle sur ce ruleset InvenTree.

    Les clés correspondent aux champs booléens de `users.models.RuleSet`. Un
    rôle inconnu est traité comme un lecteur : jamais d'écriture par défaut.
    """

    writable = ruleset in ROLE_WRITE_RULESETS.get(role, frozenset())

    return {
        "can_view": True,
        "can_add": writable,
        "can_change": writable,
        "can_delete": False,
    }


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
#: certains rôles restants (retours magasinier, tickets SAV) arriveront aux
#: sprints suivants ; on ne mappe ici que les widgets existants.
DASHBOARD_WIDGET_ROLES: dict[str, set[str]] = {
    "inventree-location-organisation": {ADMIN, GESTIONNAIRE, ORGANISATEUR, LECTEUR},
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
    # DIS-01 le destine au pilotage de l'activité : gestionnaire et lecteur,
    # plus l'admin. Le magasinier et le livreur ont leurs propres écrans
    # d'exploitation, l'organisateur ne suit que ses manifestations.
    "inventree-location-calendrier": {ADMIN, GESTIONNAIRE, LECTEUR},
    "inventree-location-ramassages": {
        ADMIN,
        GESTIONNAIRE,
        MAGASINIER,
        LIVREUR,
    },
    "inventree-location-conflicts": {ADMIN, GESTIONNAIRE, LECTEUR},
    "inventree-location-stock-alerts": {ADMIN, GESTIONNAIRE, MAGASINIER, LECTEUR},
    "inventree-location-deliveries": {ADMIN, GESTIONNAIRE, LIVREUR},
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

    return {key for key, allowed in DASHBOARD_WIDGET_ROLES.items() if owned & allowed}
