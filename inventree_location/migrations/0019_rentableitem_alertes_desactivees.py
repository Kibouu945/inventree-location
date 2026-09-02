"""Ajoute le booléen « alertes désactivées » aux articles louables (CDC V06)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Coupe-circuit des alertes de seuil, demandé par le CDC pour CONSO-01."""

    dependencies = [
        ("inventree_location", "0018_scrum112_sav_stock_reel"),
    ]

    operations = [
        migrations.AddField(
            model_name="rentableitem",
            name="alertes_desactivees",
            field=models.BooleanField(
                default=False, verbose_name="alertes désactivées"
            ),
        ),
    ]
