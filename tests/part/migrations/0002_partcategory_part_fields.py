"""Ajoute PartCategory + champs description/category au Part factice (tests)."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("part", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="PartCategory",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
            ],
            options={},
        ),
        migrations.AddField(
            model_name="part",
            name="description",
            field=models.CharField(blank=True, default="", max_length=250),
        ),
        migrations.AddField(
            model_name="part",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="parts",
                to="part.partcategory",
            ),
        ),
    ]
