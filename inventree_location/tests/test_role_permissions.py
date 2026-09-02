"""Droits InvenTree (RuleSet) attendus par rôle métier.

Vérifie ``roles.ruleset_permissions`` — la matrice pure dont
``permissions_provisioning.apply_role_permissions`` n'est que la pose en base
(``users.models.RuleSet`` appartient au cœur d'InvenTree, absent de la suite).

Contexte : les groupes du plugin ne portaient aucun droit InvenTree, ce qui
masquait le bouton « nouveau fournisseur » sur les écrans natifs — la fiche
fournisseur (`company_company`) relève du ruleset ``purchase_order``.
"""

from __future__ import annotations

import pytest

from inventree_location import permissions_provisioning, roles

#: Les 11 rulesets déclarés par InvenTree 1.5. La liste n'est pas utilisée pour
#: piloter le code (qui parcourt ce que l'hôte a créé), seulement pour balayer
#: des cas réalistes ici.
RULESETS = (
    "admin",
    "part_category",
    "part",
    "bom",
    "stock_location",
    "stock",
    "build",
    "purchase_order",
    "sales_order",
    "return_order",
    "transfer_order",
)


def test_tous_les_roles_ont_une_entree():
    """La matrice couvre les 8 personas, sans rôle oublié ni rôle en trop."""

    assert set(roles.ROLE_WRITE_RULESETS) == set(roles.ALL_ROLES)


@pytest.mark.parametrize("role", roles.ALL_ROLES)
@pytest.mark.parametrize("ruleset", RULESETS)
def test_lecture_toujours_accordee(role, ruleset):
    """Aucun rôle métier n'est aveugle : la lecture est acquise partout."""

    assert roles.ruleset_permissions(role, ruleset)["can_view"] is True


@pytest.mark.parametrize("role", roles.ALL_ROLES)
@pytest.mark.parametrize("ruleset", RULESETS)
def test_suppression_jamais_accordee(role, ruleset):
    """Le back-office désactive, il ne supprime pas (SCRUM-111)."""

    assert roles.ruleset_permissions(role, ruleset)["can_delete"] is False


@pytest.mark.parametrize("role", [roles.ADMIN, roles.ACHETEUR])
def test_achats_ouverts_a_l_admin_et_a_l_acheteur(role):
    """Le blocage remonté par le client : créer une fiche fournisseur.

    `company_company` relève de `purchase_order` ; sans `can_add`, InvenTree
    n'affiche pas le bouton de création.
    """

    droits = roles.ruleset_permissions(role, "purchase_order")

    assert droits["can_add"] is True
    assert droits["can_change"] is True


@pytest.mark.parametrize(
    "role",
    [
        roles.GESTIONNAIRE,
        roles.MAGASINIER,
        roles.LIVREUR,
        roles.SAV,
        roles.ORGANISATEUR,
        roles.LECTEUR,
    ],
)
def test_achats_en_lecture_pour_les_autres_roles(role):
    """Le CDC confie les achats à l'acheteur ; les autres consultent.

    Le gestionnaire « vérifie les commandes fournisseurs et tarifs » (CDC V06,
    personas) : c'est de la lecture, pas de la saisie.
    """

    droits = roles.ruleset_permissions(role, "purchase_order")

    assert droits["can_add"] is False
    assert droits["can_change"] is False


def test_acheteur_ne_touche_pas_au_catalogue_ni_au_stock():
    """L'acheteur commande ; il ne réécrit ni les objets ni les stocks."""

    for ruleset in ("part", "part_category", "stock", "stock_location"):
        droits = roles.ruleset_permissions(roles.ACHETEUR, ruleset)

        assert droits["can_add"] is False, ruleset
        assert droits["can_change"] is False, ruleset


@pytest.mark.parametrize(
    "role", [roles.ADMIN, roles.GESTIONNAIRE, roles.MAGASINIER]
)
@pytest.mark.parametrize(
    "ruleset", ["part", "part_category", "stock", "stock_location"]
)
def test_catalogue_et_stock_ouverts_aux_roles_d_exploitation(role, ruleset):
    """Créer une Part, ranger du stock, déclarer un sous-emplacement."""

    droits = roles.ruleset_permissions(role, ruleset)

    assert droits["can_add"] is True
    assert droits["can_change"] is True


def test_administration_invented_reste_en_lecture():
    """Le ruleset `admin` couvre les tables d'authentification.

    Le back-office du plugin gère les comptes via son API ; ouvrir ces tables
    dans les écrans natifs n'apporte rien et élargit la surface.
    """

    droits = roles.ruleset_permissions(roles.ADMIN, "admin")

    assert droits["can_add"] is False
    assert droits["can_change"] is False


def test_ruleset_inconnu_retombe_en_lecture_seule():
    """Un ruleset ajouté par une version future d'InvenTree n'ouvre rien."""

    droits = roles.ruleset_permissions(roles.ADMIN, "ruleset_qui_n_existe_pas")

    assert droits == {
        "can_view": True,
        "can_add": False,
        "can_change": False,
        "can_delete": False,
    }


def test_role_inconnu_traite_comme_un_lecteur():
    """Un groupe Django hors plugin ne gagne aucun droit d'écriture."""

    droits = roles.ruleset_permissions("stagiaire", "purchase_order")

    assert droits["can_add"] is False
    assert droits["can_change"] is False


def test_pose_inactive_hors_stack_inventree():
    """Sans InvenTree installé, la pose ne fait rien plutôt que de casser.

    C'est le cas de cette suite : `users.models` n'existe pas ici.
    """

    assert permissions_provisioning.apply_role_permissions() == []