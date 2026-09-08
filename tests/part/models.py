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
    """Catégorie d'articles, avec sa hiérarchie.

    En production `PartCategory` hérite d'`InvenTreeTree` (MPTT) et expose
    `parent` + `get_descendants()`. Le double reprend les deux : le catalogue
    étend désormais un filtre de catégorie à ses sous-catégories (recette du
    07/09/2026, remarque 4 — « reprendre le type de recherche fait pour le
    catalogue avec les libellés et les catégories, les sous-catégories »), et
    cette cascade doit être vérifiable hors container.
    """

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
        """Branche entière sous cette catégorie, en queryset.

        MPTT le fait en une requête sur les bornes de l'arbre ; ici on descend
        niveau par niveau. C'est plus lent, mais le contrat rendu est le même —
        un queryset de `PartCategory` — et c'est lui que le code de production
        consomme.
        """

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
    # Photo de l'objet. En production c'est un `StdImageField` (InvenTree y
    # génère des vignettes 128 et 256 px) ; un `ImageField` suffit ici, le
    # plugin ne fait qu'affecter le fichier et relire `.url`. Mêmes `null` et
    # `blank` que le champ natif, pour que les tests voient le même défaut.
    image = models.ImageField(
        upload_to="part_images", null=True, blank=True, default=""
    )
    # Seuil de réapprovisionnement natif d'InvenTree, repli du seuil bas du
    # plugin quand celui-ci n'est pas renseigné (recette du 07/09/2026,
    # remarque 11 : le client avait rempli ce champ-ci, nous ne lisions que le
    # nôtre). Même type qu'en production — un `DecimalField`, pas un entier :
    # `StockAlertListView._seuil_bas` doit le convertir, autant que les tests
    # le voient tel quel.
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
