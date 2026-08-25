from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventree_location", "0010_remove_rentableitem_stock_total"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="is_archived",
            field=models.BooleanField(default=False, verbose_name="archivée"),
        ),
        migrations.AddIndex(
            model_name="reservation",
            index=models.Index(fields=["statut"], name="resa_statut_idx"),
        ),
        migrations.AddIndex(
            model_name="reservation",
            index=models.Index(fields=["date_retrait_prevue"], name="resa_retrait_idx"),
        ),
        migrations.AddIndex(
            model_name="reservation",
            index=models.Index(fields=["date_retour_prevue"], name="resa_retour_idx"),
        ),
        migrations.AddIndex(
            model_name="reservation",
            index=models.Index(fields=["is_archived"], name="resa_archived_idx"),
        ),
    ]
