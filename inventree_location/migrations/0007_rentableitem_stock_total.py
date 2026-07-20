"""Add stock_total field to RentableItem."""

from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):
    """Migration adding stock_total to rentable items."""

    dependencies = [
        ("inventree_location", "0006_reservation_status_log"),
    ]

    operations = [
        migrations.AddField(
            model_name="rentableitem",
            name="stock_total",
            field=models.PositiveIntegerField(
                default=0,
                verbose_name=_("stock total"),
                help_text=_("Stock total disponible pour la location."),
            ),
        ),
    ]
