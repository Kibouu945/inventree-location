"""Assignation des livraisons et journal d'état (US-18 / US-19)."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventree_location", "0021_retour_sans_redondance"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="date_assignation",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="date d'assignation"
            ),
        ),
        migrations.AddField(
            model_name="reservation",
            name="etat_livraison",
            field=models.CharField(
                blank=True,
                choices=[
                    ("assignee", "Assignée"),
                    ("en_cours", "En cours de livraison"),
                    ("livree", "Livrée"),
                    ("probleme", "Problème signalé"),
                ],
                default="",
                max_length=20,
                verbose_name="état de la livraison",
            ),
        ),
        migrations.AddField(
            model_name="reservation",
            name="livreur_assigne",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="livraisons_assignees",
                to=settings.AUTH_USER_MODEL,
                verbose_name="livreur assigné",
            ),
        ),
        migrations.CreateModel(
            name="LivraisonStatusLog",
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
                    "from_etat",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("assignee", "Assignée"),
                            ("en_cours", "En cours de livraison"),
                            ("livree", "Livrée"),
                            ("probleme", "Problème signalé"),
                        ],
                        default="",
                        max_length=20,
                        verbose_name="ancien état",
                    ),
                ),
                (
                    "to_etat",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("assignee", "Assignée"),
                            ("en_cours", "En cours de livraison"),
                            ("livree", "Livrée"),
                            ("probleme", "Problème signalé"),
                        ],
                        default="",
                        max_length=20,
                        verbose_name="nouvel état",
                    ),
                ),
                (
                    "commentaire",
                    models.TextField(
                        blank=True, default="", verbose_name="commentaire"
                    ),
                ),
                (
                    "photo",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="inventree_location/livraisons/%Y/%m/",
                        verbose_name="photo",
                    ),
                ),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="livraison_status_changes",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="modifié par",
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="livraison_status_logs",
                        to="inventree_location.reservation",
                        verbose_name="réservation",
                    ),
                ),
            ],
            options={
                "verbose_name": "log d'état de livraison",
                "verbose_name_plural": "logs d'état de livraison",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["reservation", "created_at"],
                        name="livraison_status_log_idx",
                    )
                ],
            },
        ),
    ]
