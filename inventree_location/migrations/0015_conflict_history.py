from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("part", "0001_initial"),
        ("inventree_location", "0014_reservation_indexes_and_archiving"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ConflictHistory",
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
                    "conflict_type",
                    models.CharField(
                        choices=[
                            ("stock", "Conflit de stock"),
                            ("location", "Conflit de lieu"),
                        ],
                        max_length=20,
                        verbose_name="type de conflit",
                    ),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[("open", "Ouvert"), ("resolved", "Résolu")],
                        default="open",
                        max_length=20,
                        verbose_name="état",
                    ),
                ),
                (
                    "period_start",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="début période"
                    ),
                ),
                (
                    "period_end",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="fin période"
                    ),
                ),
                (
                    "location_key",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="clé de lieu",
                    ),
                ),
                (
                    "details",
                    models.JSONField(blank=True, default=dict, verbose_name="détails"),
                ),
                (
                    "resolved_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="résolu le"
                    ),
                ),
                (
                    "resolution_note",
                    models.TextField(
                        blank=True, default="", verbose_name="note de résolution"
                    ),
                ),
                (
                    "conflicting_reservation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conflicted_by_history",
                        to="inventree_location.reservation",
                        verbose_name="réservation en conflit",
                    ),
                ),
                (
                    "part",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="conflict_history",
                        to="part.part",
                        verbose_name="article",
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conflict_history",
                        to="inventree_location.reservation",
                        verbose_name="réservation",
                    ),
                ),
                (
                    "resolved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="resolved_conflicts",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="résolu par",
                    ),
                ),
            ],
            options={
                "verbose_name": "historique de conflit",
                "verbose_name_plural": "historiques de conflit",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="conflicthistory",
            index=models.Index(
                fields=["conflict_type", "state"], name="conflict_type_state_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="conflicthistory",
            index=models.Index(
                fields=["reservation", "state"], name="conflict_resa_state_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="conflicthistory",
            index=models.Index(fields=["created_at"], name="conflict_created_at_idx"),
        ),
    ]
