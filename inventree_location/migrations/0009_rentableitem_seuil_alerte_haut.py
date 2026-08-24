from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventree_location", "0008_remove_lieu_prestation_prestation_lieu_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="rentableitem",
            name="seuil_alerte_haut",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="seuil d'alerte haut",
            ),
        ),
    ]
