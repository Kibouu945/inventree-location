
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("inventree_location", "0010_remove_rentableitem_stock_total"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReturnIncident",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="date de création"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="date de modification"
                    ),
                ),
                (
                    "type",
                    models.CharField(
                        choices=[("missing", "Manquant"), ("broken", "Cassé")],
                        max_length=20,
                        verbose_name="type d'incident",
                    ),
                ),
                ("qty", models.PositiveIntegerField(verbose_name="quantité")),
                (
                    "comment",
                    models.TextField(
                        blank=True, default="", verbose_name="commentaire"
                    ),
                ),
                (
                    "reported_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        verbose_name="date de signalement",
                    ),
                ),
                (
                    "bill_client",
                    models.BooleanField(
                        default=False, verbose_name="facturer au client"
                    ),
                ),
                (
                    "line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="incidents",
                        to="inventree_location.lignereservation",
                        verbose_name="ligne de réservation",
                    ),
                ),
                (
                    "reported_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reported_incidents",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="signalé par",
                    ),
                ),
            ],
            options={
                "verbose_name": "incident de retour",
                "verbose_name_plural": "incidents de retour",
                "ordering": ["-reported_at"],
            },
        ),
    ]