"""Donne un statut aux prestations déjà en base.

`Prestation.statut` arrive avec un défaut à `brouillon`. Sans reprise, toutes
les prestations existantes s'afficheraient en brouillon alors que certaines ont
déjà des réservations validées, voire livrées et clôturées.

La règle se lit sur ce qui est observable : le statut de la manifestation pour
l'annulation, et l'état des réservations pour le reste.
"""

from django.db import migrations

#: Statuts de réservation qui prouvent qu'une prestation est engagée.
ENGAGEE = ("validee", "livree", "retournee", "cloturee")


def promouvoir(apps, schema_editor):
    Prestation = apps.get_model("inventree_location", "Prestation")

    annulees = 0
    confirmees = 0

    for prestation in Prestation.objects.select_related("manifestation").iterator():
        if prestation.manifestation.statut == "annulee":
            statut = "annulee"
            annulees += 1
        elif prestation.reservations.filter(statut__in=ENGAGEE).exists():
            statut = "confirmee"
            confirmees += 1
        else:
            continue

        Prestation.objects.filter(pk=prestation.pk).update(statut=statut)

    if annulees or confirmees:
        print(
            f"  inventree-location : {confirmees} prestation(s) confirmée(s), "
            f"{annulees} annulée(s)"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("inventree_location", "0024_champs_additifs"),
    ]

    # Irréversible au sens métier : on ne sait pas quelles prestations étaient
    # en brouillon avant la reprise. Même parti que `0021`.
    operations = [migrations.RunPython(promouvoir, migrations.RunPython.noop)]
