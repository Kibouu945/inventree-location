"""Le stock total d'un article vient d'InvenTree, pas du plugin.

`RentableItem` ne porte plus de compteur : la quantité louable est la somme
des `StockItem` réellement en stock dont le statut est louable.
"""

from __future__ import annotations

import pytest

from inventree_location.conflicts import RENTAL_STOCK_STATUSES, get_part_total_stock
from inventree_location.models import RentableItem
from inventree_location.tests.factories import (
    STATUT_ATTENTION,
    STATUT_DETRUIT,
    STATUT_ENDOMMAGE,
    STATUT_OK,
    STATUT_QUARANTAINE,
    STATUT_RETOURNE,
    mettre_en_stock,
)

from part.models import Part


@pytest.fixture
def part(db):
    part = Part.objects.create(name="Tente 4 places")
    RentableItem.objects.create(part=part, is_rentable=True)
    return part


@pytest.mark.django_db
class TestGetPartTotalStock:
    def test_no_stock_item_means_zero(self, part):
        """Un article déclaré louable mais jamais mis en stock vaut 0."""

        assert get_part_total_stock(part) == 0

    def test_sums_every_stock_item(self, part):
        """Le parc peut être éclaté en plusieurs exemplaires."""

        mettre_en_stock(part, 4)
        mettre_en_stock(part, 6)

        assert get_part_total_stock(part) == 10

    def test_returned_items_are_lendable_again(self, part):
        mettre_en_stock(part, 3, status=STATUT_RETOURNE)

        assert get_part_total_stock(part) == 3

    @pytest.mark.parametrize(
        "statut",
        [STATUT_ENDOMMAGE, STATUT_ATTENTION, STATUT_DETRUIT, STATUT_QUARANTAINE],
    )
    def test_unusable_items_are_excluded(self, part, statut):
        """« Seules les réservations suivantes voient le stock réellement bon »."""

        mettre_en_stock(part, 5, status=STATUT_OK)
        mettre_en_stock(part, 7, status=statut)

        assert get_part_total_stock(part) == 5

    def test_rental_statuses_are_a_subset_of_inventree_available(self):
        """Le métier est plus strict qu'InvenTree, jamais plus permissif."""

        from stock.models import StockItem

        inventree_available = dict(StockItem.IN_STOCK_FILTER.children)["status__in"]

        assert set(RENTAL_STOCK_STATUSES) <= set(inventree_available)

    def test_zero_quantity_item_is_ignored(self, part):
        """Un exemplaire épuisé ne compte pas (IN_STOCK_FILTER : quantity > 0)."""

        mettre_en_stock(part, 0)

        assert get_part_total_stock(part) == 0

    def test_item_held_by_a_customer_is_out_of_stock(self, part):
        """Sorti du stock côté InvenTree → hors du parc louable."""

        from stock.models import StockItem

        mettre_en_stock(part, 5)
        chez_le_client = mettre_en_stock(part, 4)
        StockItem.objects.filter(pk=chez_le_client.pk).update(customer=1)

        assert get_part_total_stock(part) == 5

    def test_rentable_item_no_longer_carries_a_quantity(self, part):
        """Garde-fou : le compteur parallèle ne doit pas réapparaître."""

        assert not hasattr(RentableItem, "stock_total")
        assert "stock_total" not in [
            field.name for field in RentableItem._meta.get_fields()
        ]
