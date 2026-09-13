"""Ajoute la hiérarchie des catégories au double de test (recette du 07/09/2026).

Le catalogue étend un filtre de catégorie à ses sous-catégories (remarque 4).
Sans `parent` ni `get_descendants`, la cascade partait en repli silencieux et
n'était pas vérifiable.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("part", "0005_part_minimum_stock")]

    operations = [
        migrations.AddField(
            model_name="partcategory",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="children",
                to="part.partcategory",
            ),
        ),
    ]
