"""Modèles `part` minimaux — suffisent aux FK et aux requêtes catalogue.

En production ce label `part` correspond à l'app native d'InvenTree. On
fournit ici un strict minimum (Part + PartCategory) pour que les FK
`"part.Part"` du plugin résolvent et que le catalogue soit testable hors
container InvenTree.

Les champs repris sont exactement ceux que le plugin lit ou écrit — dont
`link`, `salable` et `virtual`, que le back-office Parts (SCRUM-111) pose à la
création. Compléter ce double vaut mieux que garder des gardes
« si le champ existe » dans le code de production.
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
    link = models.CharField(max_length=200, blank=True, default="")
    active = models.BooleanField(default=True)
    salable = models.BooleanField(default=False)
    virtual = models.BooleanField(default=False)
    # Photo de l'objet. En production c'est un `StdImageField` (InvenTree y
    # génère des vignettes 128 et 256 px) ; un `ImageField` suffit ici, le
    # plugin ne fait qu'affecter le fichier et relire `.url`. Mêmes `null` et
    # `blank` que le champ natif, pour que les tests voient le même défaut.
    image = models.ImageField(
        upload_to="part_images", null=True, blank=True, default=""
    )
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
