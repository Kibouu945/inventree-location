"""Ajoute link / salable / virtual au Part factice (back-office Parts, SCRUM-111)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("part", "0002_partcategory_part_fields")]

    operations = [
        migrations.AddField(
            model_name="part",
            name="link",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="part",
            name="salable",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="part",
            name="virtual",
            field=models.BooleanField(default=False),
        ),
    ]
