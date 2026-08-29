"""Fige le vocabulaire de `etat_retour` en `choices` (cf. `EtatRetour`)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Aucun changement de colonne : seul l'état Django est mis à jour."""

    dependencies = [
        ("inventree_location", "0019_rentableitem_alertes_desactivees"),
    ]

    operations = [
        migrations.AlterField(
            model_name="lignereservation",
            name="etat_retour",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ok", "Rendu conforme"),
                    ("manquant", "Manquant"),
                    ("casse", "Cassé"),
                ],
                default="",
                max_length=20,
                verbose_name="état du retour",
            ),
        ),
    ]
