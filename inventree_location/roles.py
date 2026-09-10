"""Rôles et personas du plugin (TR-03).

Les rôles sont matérialisés par des groupes Django (`auth.Group`).
Ce module centralise les noms de rôles et les helpers de lecture.

Personas du CDC :
- admin         : CRUD complet + configuration du plugin
- gestionnaire  : manifestations / prestations / réservations + arbitrage conflits
- magasinier    : check-in retours + stock
- livreur       : tournées + statuts livraison / ramassage + Maps
- sav           : tickets réparation + historique
- lecteur       : lecture seule événement / stock
- acheteur      : achats / besoins matériel
"""

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
    LECTEUR: frozenset(),
}


#: Rulesets InvenTree **visibles** par rôle — et donc entrées de la barre de
#: navigation native : ses onglets sont conditionnés à `hasViewRole(...)`
#: (`getNavTabs`, InvenTree `src/defaults/links.tsx`). Aucun patch nécessaire.
#:
#:     Composants ← part | part_category      Achats ← purchase_order
#:     Stock      ← stock | stock_location    Ventes ← sales_order | return_order
#:     Fabrication ← build                    Dashboard : jamais conditionné
#:
#: Un ruleset absent d'un rôle est **invisible** — renversement du défaut
#: précédent, où tout le monde voyait tout. `bom` accompagne `part` (sinon
#: l'onglet BOM d'une fiche répond 403), et `part_category` est requis par le
#: filtre catégories du catalogue (`/api/part/category/`).
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


def ruleset_permissions(role: str, ruleset: str) -> dict[str, bool]:
    """Droits attendus pour ce rôle sur ce ruleset InvenTree.

    Rôle inconnu : ni lecture ni écriture. La lecture est accordée
    explicitement ; écrire implique lire, sinon `RuleSet.save()` — qui complète
    les droits impliqués — remettrait la lecture dans notre dos.
    """

    writable = ruleset in ROLE_WRITE_RULESETS.get(role, frozenset())
    viewable = ruleset in ROLE_VIEW_RULESETS.get(role, frozenset())

    return {
        "can_view": viewable or writable,
        "can_add": writable,
        "can_change": writable,
        "can_delete": False,
    }


def user_roles(user) -> set[str]:
    """Rôles plugin de l'utilisateur.

    Un ensemble, et non une valeur : un compte porte **un** rôle métier
    (décision du 09/09/2026), mais rien n'empêche un groupe Django hors plugin
    de traîner sur son compte, et l'ensemble peut être vide.
    """

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


def sees_only_deliverable_reservations(user) -> bool:
    """Vrai pour un livreur : il ne voit que les réservations validées.

    Avec le rôle unique, c'est une simple appartenance. La fonction portait
    auparavant la liste des rôles qui voient tout, pour traiter le cas « livreur
    qui cumule gestionnaire » — un cas qui ne peut plus se produire.
    """

    if getattr(user, "is_superuser", False):
        return False

    return LIVREUR in user_roles(user)


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
    # Un seul widget : le poste de travail du rôle, qui porte les écrans métier
    # dans sa propre navigation. Le client a refusé l'empilement de vignettes
    # (revue du 09/09/2026). `sav` attend ses écrans.
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
