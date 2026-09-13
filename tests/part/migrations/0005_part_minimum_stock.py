"""Ajoute le stock minimum natif au Part factice (recette du 07/09/2026).

Le plugin ne lisait que son propre `RentableItem.seuil_alerte_bas` et ignorait
`Part.minimum_stock`, que le client avait renseigné. Le double de test doit
porter le champ pour que le repli soit vérifiable hors container InvenTree.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("part", "0004_part_image")]

    operations = [
        migrations.AddField(
            model_name="part",
            name="minimum_stock",
            field=models.DecimalField(decimal_places=6, default=0, max_digits=19),
        ),
    ]
