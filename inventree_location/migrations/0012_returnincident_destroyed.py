"""Add destroyed type to return incident choices."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add destroyed type to ReturnIncidentType choices."""

    dependencies = [
        ("inventree_location", "0011_returnincident"),
    ]

    operations = [
        migrations.AlterField(
            model_name="returnincident",
            name="type",
            field=models.CharField(
                choices=[
                    ("missing", "Manquant"),
                    ("broken", "Cassé"),
                    ("destroyed", "Détruit"),
                ],
                max_length=20,
                verbose_name="type d'incident",
            ),
        ),
    ]