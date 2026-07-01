"""Add reservation status workflow log."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):
    """Migration adding reservation status log and annulee status."""

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("inventree_location", "0003_create_role_groups"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reservation",
            name="statut",
            field=models.CharField(
                choices=[
                    ("brouillon", "Brouillon"),
                    ("soumise", "Soumise"),
                    ("validee", "Validée"),
                    ("refusee", "Refusée"),
                    ("annulee", "Annulée"),
                    ("livree", "Livrée"),
                    ("retournee", "Retournée"),
                    ("cloturee", "Clôturée"),
                ],
                default="brouillon",
                max_length=20,
                verbose_name=_("statut"),
            ),
        ),
        migrations.CreateModel(
            name="ReservationStatusLog",
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
                        auto_now_add=True,
                        verbose_name=_("créé le"),
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name=_("mis à jour le"),
                    ),
                ),
                (
                    "from_status",
                    models.CharField(
                        choices=[
                            ("brouillon", "Brouillon"),
                            ("soumise", "Soumise"),
                            ("validee", "Validée"),
                            ("refusee", "Refusée"),
                            ("annulee", "Annulée"),
                            ("livree", "Livrée"),
                            ("retournee", "Retournée"),
                            ("cloturee", "Clôturée"),
                        ],
                        max_length=20,
                        verbose_name=_("ancien statut"),
                    ),
                ),
                (
                    "to_status",
                    models.CharField(
                        choices=[
                            ("brouillon", "Brouillon"),
                            ("soumise", "Soumise"),
                            ("validee", "Validée"),
                            ("refusee", "Refusée"),
                            ("annulee", "Annulée"),
                            ("livree", "Livrée"),
                            ("retournee", "Retournée"),
                            ("cloturee", "Clôturée"),
                        ],
                        max_length=20,
                        verbose_name=_("nouveau statut"),
                    ),
                ),
                (
                    "comment",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name=_("commentaire"),
                    ),
                ),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reservation_status_changes",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name=_("modifié par"),
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_logs",
                        to="inventree_location.reservation",
                        verbose_name=_("réservation"),
                    ),
                ),
            ],
            options={
                "verbose_name": _("log de statut de réservation"),
                "verbose_name_plural": _("logs de statut de réservation"),
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["reservation", "created_at"],
                        name="resa_status_log_idx",
                    ),
                ],
            },
        ),
    ]
