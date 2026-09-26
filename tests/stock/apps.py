"""App Django factice fournissant un `StockItem` minimal pour les tests."""

from django.apps import AppConfig


class StockConfig(AppConfig):
    name = "stock"
    label = "stock"
    verbose_name = "Stock (fake for tests)"
