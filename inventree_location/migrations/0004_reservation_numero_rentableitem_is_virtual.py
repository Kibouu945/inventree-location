"""Ajoute RentableItem.is_virtual et Reservation.numero (RES-AAAA-NNNN).

Le numéro est ajouté d'abord sans contrainte d'unicité, puis rétro-rempli
pour les réservations existantes (une par une, par ordre de création, en
respectant le compteur annuel), avant d'appliquer la contrainte unique.
"""

from django.db import migrations, models


def backfill_numeros(apps, schema_editor):
    Reservation = apps.get_model("inventree_location", "Reservation")

    counters = {}

    for reservation in Reservation.objects.order_by("date_demande", "pk"):
        year = reservation.date_demande.year
        counters[year] = counters.get(year, 0) + 1
        reservation.numero = f"RES-{year}-{counters[year]:04d}"
        reservation.save(update_fields=["numero"])


def noop_reverse(apps, schema_editor):
    """Rien à défaire : la colonne numero sera supprimée par la migration inverse."""


class Migration(migrations.Migration):
    dependencies = [
        ("inventree_location", "0003_create_role_groups"),
    ]

    operations = [
        migrations.AddField(
            model_name="rentableitem",
            name="is_virtual",
            field=models.BooleanField(default=False, verbose_name="article virtuel"),
        ),
        migrations.AddField(
            model_name="reservation",
            name="numero",
            field=models.CharField(
                blank=True,
                default="",
                editable=False,
                max_length=20,
                verbose_name="numéro",
            ),
        ),
        migrations.RunPython(backfill_numeros, noop_reverse),
        migrations.AlterField(
            model_name="reservation",
            name="numero",
            field=models.CharField(
                blank=True,
                default="",
                editable=False,
                max_length=20,
                unique=True,
                verbose_name="numéro",
            ),
        ),
    ]
