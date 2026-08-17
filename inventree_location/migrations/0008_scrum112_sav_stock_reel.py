# Generated manually for SCRUM-112

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inventree_location", "0007_rentableitem_stock_total"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("part", "0047_alter_part_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="lignereservation",
            name="quantite_ramassee",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Quantité ramassée en bon état, réintégrable au stock réel.",
                verbose_name="quantité ramassée bonne",
            ),
        ),
        migrations.AddField(
            model_name="lignereservation",
            name="quantite_sav",
            field=models.PositiveIntegerField(
                default=0,
                verbose_name="quantité à mettre au SAV",
            ),
        ),
        migrations.AddField(
            model_name="lignereservation",
            name="quantite_detruite",
            field=models.PositiveIntegerField(
                default=0,
                verbose_name="quantité détruite",
            ),
        ),
        migrations.AddField(
            model_name="lignereservation",
            name="quantite_manquante",
            field=models.PositiveIntegerField(
                default=0,
                verbose_name="quantité manquante",
            ),
        ),
        migrations.AddField(
            model_name="lignereservation",
            name="facturer_client",
            field=models.BooleanField(
                default=False,
                verbose_name="facturer le client",
            ),
        ),
        migrations.CreateModel(
            name="SavTicket",
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
                        verbose_name="date de création",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="date de modification",
                    ),
                ),
                (
                    "type_ticket",
                    models.CharField(
                        choices=[
                            ("reparation", "Réparation"),
                            ("destruction", "Destruction"),
                        ],
                        default="reparation",
                        max_length=20,
                        verbose_name="type de ticket",
                    ),
                ),
                (
                    "statut",
                    models.CharField(
                        choices=[
                            ("ouvert", "Ouvert"),
                            ("en_reparation", "En réparation"),
                            ("repare", "Réparé"),
                            ("detruit", "Détruit"),
                            ("cloture", "Clôturé"),
                        ],
                        default="ouvert",
                        max_length=20,
                        verbose_name="statut",
                    ),
                ),
                (
                    "quantite",
                    models.PositiveIntegerField(
                        default=1,
                        verbose_name="quantité",
                    ),
                ),
                (
                    "facturer_client",
                    models.BooleanField(
                        default=False,
                        verbose_name="facturer le client",
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="description",
                    ),
                ),
                (
                    "diagnostic",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="diagnostic",
                    ),
                ),
                (
                    "resolution",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="résolution",
                    ),
                ),
                (
                    "closed_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="date de clôture",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sav_tickets_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="créé par",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sav_tickets_updated",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="modifié par",
                    ),
                ),
                (
                    "ligne_reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sav_tickets",
                        to="inventree_location.lignereservation",
                        verbose_name="ligne de réservation",
                    ),
                ),
                (
                    "part",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="location_sav_tickets",
                        to="part.part",
                        verbose_name="part",
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sav_tickets",
                        to="inventree_location.reservation",
                        verbose_name="réservation",
                    ),
                ),
            ],
            options={
                "verbose_name": "ticket SAV",
                "verbose_name_plural": "tickets SAV",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="savticket",
            constraint=models.UniqueConstraint(
                fields=("ligne_reservation", "type_ticket"),
                name="unique_sav_ticket_by_line_type",
            ),
        ),
        migrations.AddIndex(
            model_name="savticket",
            index=models.Index(
                fields=["part", "statut"],
                name="sav_part_statut_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="savticket",
            index=models.Index(
                fields=["created_at"],
                name="sav_created_at_idx",
            ),
        ),
    ]