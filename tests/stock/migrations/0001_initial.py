"""Migration initiale de l'app `stock` factice (tests uniquement)."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [("part", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="StockItem",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "quantity",
                    models.DecimalField(decimal_places=5, default=0, max_digits=15),
                ),
                ("status", models.PositiveIntegerField(default=10)),
                ("is_building", models.BooleanField(default=False)),
                ("belongs_to", models.PositiveIntegerField(blank=True, null=True)),
                ("consumed_by", models.PositiveIntegerField(blank=True, null=True)),
                ("customer", models.PositiveIntegerField(blank=True, null=True)),
                ("sales_order", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "part",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stock_items",
                        to="part.part",
                    ),
                ),
            ],
            options={},
        ),
    ]
