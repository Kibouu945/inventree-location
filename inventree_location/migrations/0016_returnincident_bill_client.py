"""Ajoute `bill_client` aux incidents de retour (SCRUM-96, rapport de pertes)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Drapeau « facturer au client » sur ReturnIncident."""

    dependencies = [
        ("inventree_location", "0015_create_acheteur_role_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="returnincident",
            name="bill_client",
            field=models.BooleanField(default=False, verbose_name="facturer au client"),
        ),
    ]
