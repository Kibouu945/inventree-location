"""Modèles `part` minimaux — suffisent aux FK et aux requêtes catalogue.

En production ce label `part` correspond à l'app native d'InvenTree. On
fournit ici un strict minimum (Part + PartCategory) pour que les FK
`"part.Part"` du plugin résolvent et que le catalogue soit testable hors
container InvenTree.
"""

from django.db import models


class PartCategory(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "part"

    def __str__(self) -> str:
        return self.name


class Part(models.Model):
    name = models.CharField(max_length=100)
    IPN = models.CharField(max_length=100, blank=True, default="")  # noqa: N815
    description = models.CharField(max_length=250, blank=True, default="")
    active = models.BooleanField(default=True)
    category = models.ForeignKey(
        PartCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="parts",
    )

    class Meta:
        app_label = "part"

    def __str__(self) -> str:
        return self.name
