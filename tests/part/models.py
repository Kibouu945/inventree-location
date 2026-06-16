"""Modèle `Part` minimal — suffit aux FK et aux requêtes `Part.objects.count()`."""

from django.db import models


class Part(models.Model):
    name = models.CharField(max_length=100)
    IPN = models.CharField(max_length=100, blank=True, default="")  # noqa: N815
    active = models.BooleanField(default=True)

    class Meta:
        app_label = "part"

    def __str__(self) -> str:
        return self.name
