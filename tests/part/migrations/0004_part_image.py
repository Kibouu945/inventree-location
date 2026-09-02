"""Ajoute la photo au Part factice (photo d'un objet, retour client du 01/09/2026)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("part", "0003_part_link_salable_virtual")]

    operations = [
        migrations.AddField(
            model_name="part",
            name="image",
            field=models.ImageField(
                blank=True, default="", null=True, upload_to="part_images"
            ),
        ),
    ]
