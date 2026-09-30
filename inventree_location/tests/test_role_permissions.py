"""Droits InvenTree (RuleSet) attendus par rôle métier."""

from __future__ import annotations

import pytest

from inventree_location import permissions_provisioning, roles

#: Les 11 rulesets déclarés par InvenTree 1.5.
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


    assert set(roles.ROLE_WRITE_RULESETS) == set(roles.ALL_ROLES)
    assert set(roles.ROLE_VIEW_RULESETS) == set(roles.ALL_ROLES)


@pytest.mark.parametrize("role", roles.ALL_ROLES)
@pytest.mark.parametrize("ruleset", RULESETS)
def test_la_lecture_suit_la_matrice_de_visibilite(role, ruleset):
    """Lecture accordée explicitement, jamais par défaut."""

    attendu = ruleset in roles.ROLE_VIEW_RULESETS[role]

    assert roles.ruleset_permissions(role, ruleset)["can_view"] is attendu


@pytest.mark.parametrize("role", roles.ALL_ROLES)
@pytest.mark.parametrize("ruleset", RULESETS)
def test_ecrire_implique_lire(role, ruleset):
    """Sinon `RuleSet.save()` rétablirait la lecture dans notre dos."""

    droits = roles.ruleset_permissions(role, ruleset)

    if droits["can_add"] or droits["can_change"]:
        assert droits["can_view"] is True


def test_la_barre_de_navigation_par_role():
    """Fige la barre horizontale par rôle : Dashboard partout, Fabrication et"""

    def onglets(role):
        vus = roles.ROLE_VIEW_RULESETS[role]
        return {
            "composantes": bool(vus & {"part", "part_category"}),
            "stock": bool(vus & {"stock", "stock_location", "transfer_order"}),
            "fabrication": "build" in vus,
            "achats": "purchase_order" in vus,
            "ventes": bool(vus & {"sales_order", "return_order"}),
        }

    assert onglets(roles.ADMIN) == {
        "composantes": True,
        "stock": True,
        "fabrication": True,
        "achats": True,
        "ventes": True,
    }
    # Le livreur ne garde que le Dashboard, donc son poste.
    assert onglets(roles.LIVREUR) == {
        "composantes": False,
        "stock": False,
        "fabrication": False,
        "achats": False,
        "ventes": False,
    }
    assert onglets(roles.ACHETEUR)["achats"] is True

    for role in (
        roles.GESTIONNAIRE,
        roles.MAGASINIER,
        roles.ACHETEUR,
        roles.SAV,
        roles.LECTEUR,
    ):
        assert onglets(role)["fabrication"] is False, role
        assert onglets(role)["ventes"] is False, role


@pytest.mark.parametrize("role", roles.ALL_ROLES)
@pytest.mark.parametrize("ruleset", RULESETS)
def test_suppression_jamais_accordee_hors_nomenclature(role, ruleset):
    """Le back-office désactive, il ne supprime pas (SCRUM-111)."""

    if (role, ruleset) == (roles.ADMIN, "bom"):
        return

    assert roles.ruleset_permissions(role, ruleset)["can_delete"] is False


def test_l_admin_compose_les_packs():
    """Recette du 27/09 : constituer un pack et y associer des éléments.

    Sans `bom` en écriture, l'onglet reste sans bouton d'ajout."""

    droits = roles.ruleset_permissions(roles.ADMIN, "bom")

    assert droits["can_add"] is True
    assert droits["can_change"] is True
    # Retirer un élément mal saisi : une ligne de nomenclature ne se désactive
    # pas, seule exception à SCRUM-111.
    assert droits["can_delete"] is True


@pytest.mark.parametrize(
    "role",
    [
        roles.GESTIONNAIRE,
        roles.MAGASINIER,
        roles.ACHETEUR,
        roles.SAV,
        roles.LECTEUR,
    ],
)
def test_les_autres_roles_consultent_les_packs(role):
    """Composer un pack définit le catalogue : c'est le geste de l'admin, comme
    rendre un article louable."""

    droits = roles.ruleset_permissions(role, "bom")

    assert droits["can_view"] is True
    assert droits["can_add"] is False
    assert droits["can_change"] is False
    assert droits["can_delete"] is False


@pytest.mark.parametrize("role", [roles.ADMIN, roles.ACHETEUR])
def test_achats_ouverts_a_l_admin_et_a_l_acheteur(role):
    """Le blocage remonté par le client : créer une fiche fournisseur."""

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
        roles.LECTEUR,
    ],
)
def test_achats_en_lecture_pour_les_autres_roles(role):
    """Le CDC confie les achats à l'acheteur ; les autres consultent."""

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


def test_administration_inventree_reste_en_lecture():
    """Le ruleset `admin` couvre les tables d'authentification."""

    droits = roles.ruleset_permissions(roles.ADMIN, "admin")

    assert droits["can_add"] is False
    assert droits["can_change"] is False


def test_ruleset_inconnu_n_ouvre_rien():
    """Un ruleset ajouté par une version future n'ouvre rien, pas même la"""

    droits = roles.ruleset_permissions(roles.ADMIN, "ruleset_qui_n_existe_pas")

    assert droits == {
        "can_view": False,
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
    """Sans InvenTree installé, la pose ne fait rien plutôt que de casser."""

    assert permissions_provisioning.apply_role_permissions() == []