"""Aides de mise en stock pour les tests.

Le stock physique appartient à InvenTree : un article n'a de quantité que par
ses `StockItem`. Hors container, c'est l'app `stock` factice (cf.
`tests/stock/`) qui les porte. Ces aides évitent de répéter la création d'un
exemplaire dans chaque fixture.
"""

from __future__ import annotations

#: Quelques statuts InvenTree utiles aux tests (cf. RENTAL_STOCK_STATUSES).
STATUT_OK = 10
STATUT_ATTENTION = 50
STATUT_ENDOMMAGE = 55
STATUT_DETRUIT = 60
STATUT_QUARANTAINE = 75
STATUT_RETOURNE = 85


def mettre_en_stock(part, quantity, *, status=STATUT_OK):
    """Crée un exemplaire en stock pour `part` et le retourne."""

    from stock.models import StockItem

    return StockItem.objects.create(part=part, quantity=quantity, status=status)


def fixer_stock(part, quantity, *, status=STATUT_OK):
    """Ramène le stock de `part` à `quantity` exactement."""

    from stock.models import StockItem

    StockItem.objects.filter(part=part).delete()

    if quantity:
        return mettre_en_stock(part, quantity, status=status)

    return None
