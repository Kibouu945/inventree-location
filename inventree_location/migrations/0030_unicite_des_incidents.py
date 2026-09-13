"""Un seul incident par ligne et par nature.

Le registre `ReturnIncident` porte un **total par nature**, pas une suite de
signalements : `projeter_incidents` lit `filter(line=..., type=...).first()`
puis écrit dessus, et tous les agrégats du stock réel somment par type. Rien ne
garantissait cette unicité en base — un POST direct sur `/returns/incidents/`
créait un second enregistrement que la projection ne voyait jamais, et que les
sommes comptaient deux fois. Tant que ce trou existait, aucun chiffre calculé
depuis le registre n'était fiable.

La déduplication **somme** les quantités du groupe dans l'enregistrement le
plus récent — celui que `projeter_incidents` aurait mis à jour, l'ordre du
modèle étant `-reported_at`. La somme, et non le maximum : `quantites_du_retour`
et le plafond du sérialiseur additionnent déjà les enregistrements, donc sommer
laisse **tous les chiffres affichés inchangés**.

Un groupe où le drapeau de refacturation diverge est le seul cas qui demande un
arbitrage : on garde `bill_client=True`, parce que perdre une décision de
facturation coûte plus cher que d'en signaler une à revoir, et on journalise les
identifiants pour qu'elle soit revue.
"""

from django.db import migrations, models
from django.db.models import Count


def dedupliquer(apps, schema_editor):
    ReturnIncident = apps.get_model("inventree_location", "ReturnIncident")

    groupes = (
        ReturnIncident.objects.values("line", "type")
        .annotate(nombre=Count("id"))
        .filter(nombre__gt=1)
    )

    fusionnes = 0
    a_revoir = []

    for groupe in groupes:
        incidents = list(
            ReturnIncident.objects.filter(
                line=groupe["line"], type=groupe["type"]
            ).order_by("-reported_at", "-id")
        )

        garde, autres = incidents[0], incidents[1:]

        total = sum(incident.qty or 0 for incident in incidents)
        facture = any(incident.bill_client for incident in incidents)

        if facture and not all(incident.bill_client for incident in incidents):
            a_revoir.append(garde.pk)

        garde.qty = total
        garde.bill_client = facture
        garde.save(update_fields=["qty", "bill_client"])

        ReturnIncident.objects.filter(pk__in=[i.pk for i in autres]).delete()
        fusionnes += len(autres)

    if fusionnes:
        print(f"  inventree-location : {fusionnes} incident(s) en doublon fusionné(s)")

    if a_revoir:
        print(
            "  inventree-location : refacturation à revoir sur les incidents "
            f"{', '.join(str(pk) for pk in a_revoir)}"
        )


class Migration(migrations.Migration):
    dependencies = [("inventree_location", "0029_suppression_du_role_organisateur")]

    operations = [
        migrations.RunPython(dedupliquer, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="returnincident",
            constraint=models.UniqueConstraint(
                fields=("line", "type"), name="incident_unique_par_ligne_et_type"
            ),
        ),
    ]
