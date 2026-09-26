"""Modèles `part` minimaux — suffisent aux FK et aux requêtes catalogue."""

from django.db import models


class PartCategory(models.Model):
    """Catégorie d'articles, avec sa hiérarchie."""

    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )

    class Meta:
        app_label = "part"

    def __str__(self) -> str:
        return self.name

    def get_descendants(self, include_self: bool = False):
        """Branche entière sous cette catégorie, en queryset."""

        ids = {self.pk} if include_self else set()
        frontiere = [self.pk]

        while frontiere:
            enfants = list(
                PartCategory.objects.filter(parent_id__in=frontiere).values_list(
                    "pk", flat=True
                )
            )
            # Une boucle dans les données ne doit pas devenir une boucle infinie.
            frontiere = [pk for pk in enfants if pk not in ids]
            ids.update(frontiere)

        return PartCategory.objects.filter(pk__in=ids)


class Part(models.Model):
    name = models.CharField(max_length=100)
    IPN = models.CharField(max_length=100, blank=True, default="")  # noqa: N815
    description = models.CharField(max_length=250, blank=True, default="")
    link = models.CharField(max_length=200, blank=True, default="")
    active = models.BooleanField(default=True)
    salable = models.BooleanField(default=False)
    virtual = models.BooleanField(default=False)
    # Photo de l'objet.
    image = models.ImageField(
        upload_to="part_images", null=True, blank=True, default=""
    )
    # Seuil de réapprovisionnement natif d'InvenTree, repli du seuil bas du
    # plugin quand celui-ci n'est pas renseigné (recette du 07/09/2026,
    minimum_stock = models.DecimalField(
        max_digits=19, decimal_places=6, default=0
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
