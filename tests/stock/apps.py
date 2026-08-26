"""App Django factice fournissant un `StockItem` minimal pour les tests.

En production, ce label `stock` correspond à l'app native d'InvenTree, qui
détient le stock physique. Le plugin l'interroge (cf.
`conflicts.get_part_total_stock`) mais ne le recrée pas : on en fournit ici le
strict minimum pour que cette requête soit testable hors container.
"""

from django.apps import AppConfig


class StockConfig(AppConfig):
    name = "stock"
    label = "stock"
    verbose_name = "Stock (fake for tests)"
