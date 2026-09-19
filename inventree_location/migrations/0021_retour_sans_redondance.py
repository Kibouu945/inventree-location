"""Supprime les sept colonnes de retour redondantes avec le registre.

Trois fonctionnalités ont ajouté leurs propres colonnes sur `LigneReservation`
pour décrire le même retour — le check-in (`quantite_retour_*`) et le ramassage
(`quantite_ramassee`, `_sav`, `_detruite`, `_manquante`, `facturer_client`) —
alors que `ReturnIncident` porte déjà « combien manque, combien est cassé,
combien est détruit, faut-il facturer ». Deux écrans pointant la même ligne
écrivaient donc deux vérités.

La migration reporte d'abord tout ce que les colonnes savaient dans le registre,
puis les supprime. `quantite_retournee` est conservée : « combien est revenu
physiquement » ne se déduit d'aucun incident.

Irréversible par nature (on ne peut pas rétablir des colonnes dont la donnée
vit désormais ailleurs sous une autre forme), d'où le `RunPython.noop` en sens
inverse : le registre reste, seules les colonnes disparaissent.
"""

from django.db import migrations, models

#: Colonnes des deux écrans → type d'incident. Les deux familles décrivent la
#: même réalité : on garde le plus grand des deux, pas la somme, sinon un retour
#: pointé deux fois doublerait ses quantités.
REPRISE = (
    (("quantite_retour_casse", "quantite_sav"), "broken"),
    (("quantite_detruite",), "destroyed"),
    (("quantite_retour_manquant", "quantite_manquante"), "missing"),
)


def reporter_dans_le_registre(apps, schema_editor):
    """Crée les incidents manquants depuis les colonnes, sans rien écraser."""

    LigneReservation = apps.get_model("inventree_location", "LigneReservation")
    ReturnIncident = apps.get_model("inventree_location", "ReturnIncident")

    for ligne in LigneReservation.objects.all().iterator():
        deja = set(
            ReturnIncident.objects.filter(line=ligne).values_list("type", flat=True)
        )

        for champs, type_incident in REPRISE:
            if type_incident in deja:
                # Le registre a déjà parlé pour ce type : il fait foi.
                continue

            quantite = max((getattr(ligne, champ, 0) or 0) for champ in champs)

            if quantite <= 0:
                continue

            ReturnIncident.objects.create(
                line=ligne,
                type=type_incident,
                qty=quantite,
                comment=ligne.commentaire or "",
                bill_client=bool(getattr(ligne, "facturer_client", False)),
            )

        # « Revenu physiquement » : ce que le ramassage ou le check-in en disait.
        revenue_ramassage = (
            (ligne.quantite_ramassee or 0)
            + (ligne.quantite_sav or 0)
            + (ligne.quantite_detruite or 0)
        )
        revenue_checkin = (ligne.quantite_retour_ok or 0) + (
            ligne.quantite_retour_casse or 0
        )
        revenue = max(revenue_ramassage, revenue_checkin, ligne.quantite_retournee or 0)

        if revenue != (ligne.quantite_retournee or 0):
            ligne.quantite_retournee = revenue
            ligne.save(update_fields=["quantite_retournee"])

    normaliser_etat_retour(apps)


#: Ancien vocabulaire de la saisie de ramassage → vocabulaire unique.
ETATS_MORTS = {"sav": "casse", "detruit": "casse", "mixte": None}


def normaliser_etat_retour(apps):
    """Réécrit les états issus de l'ancien vocabulaire de la PR #40.

    `sav`, `detruit` et `mixte` ne font plus partie de `EtatRetour` : laissés en
    base, ils s'afficheraient tels quels et échapperaient aux libellés. `mixte`
    n'a pas d'équivalent : on recalcule depuis le registre, la plus grave des
    natures l'emportant.
    """

    LigneReservation = apps.get_model("inventree_location", "LigneReservation")
    ReturnIncident = apps.get_model("inventree_location", "ReturnIncident")

    gravite = ("destroyed", "broken", "missing")
    etat_par_type = {"destroyed": "casse", "broken": "casse", "missing": "manquant"}

    for ligne in LigneReservation.objects.exclude(
        etat_retour__in=["", "ok", "manquant", "casse"]
    ).iterator():
        remplacement = ETATS_MORTS.get(ligne.etat_retour)

        if remplacement is None:
            types = set(
                ReturnIncident.objects.filter(line=ligne).values_list("type", flat=True)
            )
            remplacement = next(
                (etat_par_type[t] for t in gravite if t in types),
                "ok" if (ligne.quantite_retournee or 0) > 0 else "",
            )

        ligne.etat_retour = remplacement
        ligne.save(update_fields=["etat_retour"])


class Migration(migrations.Migration):
    atomic = False
    """Reprise des données puis suppression des colonnes."""

    dependencies = [
        ("inventree_location", "0020_alter_lignereservation_etat_retour"),
    ]

    operations = [
        migrations.RunPython(reporter_dans_le_registre, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="lignereservation",
            name="quantite_retournee",
            field=models.PositiveIntegerField(
                default=0, verbose_name="quantité revenue"
            ),
        ),
        migrations.RemoveField(model_name="lignereservation", name="quantite_ramassee"),
        migrations.RemoveField(model_name="lignereservation", name="quantite_sav"),
        migrations.RemoveField(model_name="lignereservation", name="quantite_detruite"),
        migrations.RemoveField(
            model_name="lignereservation", name="quantite_manquante"
        ),
        migrations.RemoveField(model_name="lignereservation", name="facturer_client"),
        migrations.RemoveField(
            model_name="lignereservation", name="quantite_retour_ok"
        ),
        migrations.RemoveField(
            model_name="lignereservation", name="quantite_retour_manquant"
        ),
        migrations.RemoveField(
            model_name="lignereservation", name="quantite_retour_casse"
        ),
    ]
