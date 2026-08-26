"""Tests du back-office Parts (SCRUM-111).

Points sensibles couverts :
- le stock exposé est celui d'InvenTree (`StockItem`), jamais un compteur
  local : `RentableItem.stock_total` n'existe plus depuis la migration
  `0010_remove_rentableitem_stock_total` ;
- `stock_initial` crée un vrai `StockItem` ;
- les règles métier (PACK / consommable / virtuel, seuils) tiennent aussi en
  PATCH partiel, où les champs absents valent ceux de la base ;
- accès réservé au rôle `admin`.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from part.models import Part
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate
from stock.models import StockItem

from inventree_location import roles
from inventree_location.models import RentableItem
from inventree_location.part_backoffice import (
    PartBackOfficeDetailView,
    PartBackOfficeListCreateView,
)

User = get_user_model()

PARTS_URL = "/plugin/inventree-location/backoffice/parts/"


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def admin(db):
    account = User.objects.create_user(username="patronne", password="pwd12345")
    account.groups.add(Group.objects.get(name=roles.ADMIN))
    return account


def _list(factory, user, **params):
    request = factory.get(PARTS_URL, params)
    force_authenticate(request, user=user)
    return PartBackOfficeListCreateView.as_view()(request)


def _create(factory, user, payload):
    request = factory.post(PARTS_URL, payload, format="json")
    force_authenticate(request, user=user)
    return PartBackOfficeListCreateView.as_view()(request)


def _patch(factory, user, part, payload):
    request = factory.patch(f"{PARTS_URL}{part.pk}/", payload, format="json")
    force_authenticate(request, user=user)
    return PartBackOfficeDetailView.as_view()(request, pk=part.pk)


class TestAcces:
    def test_role_non_admin_refuse(self, factory, db):
        user = User.objects.create_user(username="magasinier", password="pwd12345")
        user.groups.add(Group.objects.get(name=roles.MAGASINIER))

        assert _list(factory, user).status_code == status.HTTP_403_FORBIDDEN

    def test_admin_autorise(self, factory, admin):
        assert _list(factory, admin).status_code == status.HTTP_200_OK


class TestCreation:
    def test_creation_complete(self, factory, admin):
        response = _create(
            factory,
            admin,
            {
                "NOI": "NOI-001",
                "name": "Table pliante",
                "description": "180 cm",
                "link": "https://example.com/table",
                "active": True,
                "salable": False,
                "virtual": False,
                "is_rentable": True,
                "consommable": False,
                "seuil_alerte_bas": 2,
                "seuil_alerte_haut": 40,
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

        part = Part.objects.get(name="Table pliante")

        assert part.IPN == "NOI-001"
        assert part.link == "https://example.com/table"

        rentable = RentableItem.objects.get(part=part)

        assert rentable.is_rentable is True
        assert rentable.seuil_alerte_bas == 2
        assert rentable.seuil_alerte_haut == 40

    def test_virtuel_recopie_sur_le_rentable_item(self, factory, admin):
        _create(
            factory,
            admin,
            {"name": "Prestation montage", "virtual": True, "is_rentable": True},
        )

        part = Part.objects.get(name="Prestation montage")

        assert part.virtual is True
        assert RentableItem.objects.get(part=part).is_virtual is True

    def test_nom_obligatoire(self, factory, admin):
        response = _create(factory, admin, {"description": "sans nom"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "name" in response.data

    def test_consommable_et_virtuel_incompatibles(self, factory, admin):
        response = _create(
            factory,
            admin,
            {"name": "Impossible", "consommable": True, "virtual": True},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert Part.objects.filter(name="Impossible").exists() is False

    def test_seuil_haut_inferieur_au_seuil_bas_refuse(self, factory, admin):
        response = _create(
            factory,
            admin,
            {"name": "Seuils", "seuil_alerte_bas": 10, "seuil_alerte_haut": 5},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "seuil_alerte_haut" in response.data


class TestStock:
    def test_stock_initial_cree_un_stock_item(self, factory, admin):
        response = _create(
            factory,
            admin,
            {"name": "Chaise", "stock_initial": 12},
        )

        assert response.status_code == status.HTTP_201_CREATED

        part = Part.objects.get(name="Chaise")
        item = StockItem.objects.get(part=part)

        assert float(item.quantity) == 12.0
        # Le stock exposé est celui d'InvenTree, pas la valeur saisie.
        assert response.data["stock_total"] == 12

    def test_sans_stock_initial_aucun_stock_item(self, factory, admin):
        _create(factory, admin, {"name": "Barnum"})

        part = Part.objects.get(name="Barnum")

        assert StockItem.objects.filter(part=part).count() == 0

    def test_stock_total_suit_les_stock_items(self, factory, admin):
        part = Part.objects.create(name="Praticable")
        RentableItem.objects.create(part=part)
        StockItem.objects.create(part=part, quantity=5)
        StockItem.objects.create(part=part, quantity=3)

        response = _list(factory, admin)

        ligne = next(
            row for row in response.data["results"] if row["name"] == "Praticable"
        )

        assert ligne["stock_total"] == 8

    def test_stock_total_nest_pas_ecrivable(self, factory, admin):
        """Champ en lecture seule : une valeur envoyée est ignorée, pas persistée."""

        part = Part.objects.create(name="Tente")
        RentableItem.objects.create(part=part)

        response = _patch(factory, admin, part, {"stock_total": 99})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["stock_total"] == 0
        assert hasattr(RentableItem.objects.get(part=part), "stock_total") is False

    def test_stock_additionnel_a_ledition(self, factory, admin):
        part = Part.objects.create(name="Gradin")
        RentableItem.objects.create(part=part)
        StockItem.objects.create(part=part, quantity=2)

        response = _patch(factory, admin, part, {"stock_initial": 4})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["stock_total"] == 6


class TestEdition:
    def test_edition_des_champs_part(self, factory, admin):
        part = Part.objects.create(name="Ancien nom")
        RentableItem.objects.create(part=part)

        response = _patch(
            factory, admin, part, {"name": "Nouveau nom", "active": False}
        )

        part.refresh_from_db()

        assert response.status_code == status.HTTP_200_OK
        assert part.name == "Nouveau nom"
        assert part.active is False

    def test_edition_cree_le_rentable_item_manquant(self, factory, admin):
        part = Part.objects.create(name="Sans extension")

        response = _patch(factory, admin, part, {"consommable": True})

        assert response.status_code == status.HTTP_200_OK
        assert RentableItem.objects.get(part=part).consommable is True

    def test_patch_partiel_conserve_letat_virtuel(self, factory, admin):
        """Règle métier évaluée sur l'état réel, pas sur les seuls champs envoyés.

        Une Part déjà virtuelle ne doit pas pouvoir devenir consommable au
        prétexte que `virtual` n'est pas dans le PATCH.
        """

        part = Part.objects.create(name="Prestation", virtual=True)
        RentableItem.objects.create(part=part, is_virtual=True)

        response = _patch(factory, admin, part, {"consommable": True})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert RentableItem.objects.get(part=part).consommable is False

    def test_patch_partiel_compare_aux_seuils_enregistres(self, factory, admin):
        part = Part.objects.create(name="Seuils")
        RentableItem.objects.create(part=part, seuil_alerte_bas=10)

        response = _patch(factory, admin, part, {"seuil_alerte_haut": 4})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "seuil_alerte_haut" in response.data


class TestListe:
    @pytest.mark.parametrize(
        "terme, attendu",
        [
            ("table", 1),
            ("NOI-9", 1),
            ("pliante", 1),
            ("absent", 0),
        ],
    )
    def test_recherche(self, factory, admin, terme, attendu):
        Part.objects.create(
            name="Table", IPN="NOI-9", description="Table pliante 180 cm"
        )

        response = _list(factory, admin, search=terme)

        assert response.data["count"] == attendu

    def test_liste_paginee(self, factory, admin):
        for index in range(25):
            Part.objects.create(name=f"Article {index:02d}")

        response = _list(factory, admin)

        assert response.data["count"] == 25
        assert len(response.data["results"]) == 20
        assert response.data["next"] is not None

    def test_part_sans_rentable_item_est_listee(self, factory, admin):
        Part.objects.create(name="Orpheline")

        response = _list(factory, admin)

        ligne = next(
            row for row in response.data["results"] if row["name"] == "Orpheline"
        )

        assert ligne["is_rentable"] is False
        assert ligne["seuil_alerte_bas"] is None
        assert ligne["pack"] is False
