"""Modèle `StockItem` minimal — reproduit ce que le plugin interroge."""

from django.db import models
from django.db.models import Q


class StockItem(models.Model):
    #: Copie conforme du filtre natif InvenTree (statuts « disponibles »
    #: inclus : OK, Attention, Endommagé, Retourné).
    IN_STOCK_FILTER = Q(
        belongs_to=None,
        consumed_by=None,
        customer=None,
        is_building=False,
        quantity__gt=0,
        sales_order=None,
        status__in=[10, 50, 55, 85],
    )

    part = models.ForeignKey(
        "part.Part",
        on_delete=models.CASCADE,
        related_name="stock_items",
    )
    quantity = models.DecimalField(max_digits=15, decimal_places=5, default=0)
    status = models.PositiveIntegerField(default=10)
    is_building = models.BooleanField(default=False)
    belongs_to = models.PositiveIntegerField(null=True, blank=True)
    consumed_by = models.PositiveIntegerField(null=True, blank=True)
    customer = models.PositiveIntegerField(null=True, blank=True)
    sales_order = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        app_label = "stock"

    def __str__(self) -> str:
        return f"StockItem(part={self.part_id}, qty={self.quantity})"
