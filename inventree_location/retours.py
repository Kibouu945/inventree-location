"""État d'un retour : un vocabulaire, un registre, une déduction.

Trois fonctionnalités constatent le même fait — du matériel qui revient abîmé,
manquant ou détruit — et chacune est arrivée avec sa propre écriture :

- le **check-in retour** (SCRUM-94, PR #41) pose `quantite_retour_ok /
  _manquant / _casse` sur la ligne ;
- le **journal d'incidents** (SCRUM-93/96, PR #45 et #47) tient la table
  `ReturnIncident`, que lisent l'historique 90 jours, le rapport de retour, son
  PDF et le rapport de pertes ;
- la **saisie du ramassage** (SCRUM-112, PR #40) pose `quantite_ramassee /
  _sav / _detruite / _manquante` sur la même ligne.

Résultat avant ce module : `etat_retour` avait **trois écrivains et trois
vocabulaires** (`casse` d'un côté, `sav` et `detruit` de l'autre, `mixte` chez
le troisième), la règle du check-in était écrite deux fois, et deux écrans
pouvaient décrire le même retour différemment.

Ce module fixe les trois points de convergence :

1. **Un vocabulaire** — `EtatRetour` sur le modèle. `sav` et `detruit`
   disparaissent : du point de vue de la ligne, un objet parti au SAV ou détruit
   est un objet cassé. La nuance vit dans les incidents et les tickets SAV, pas
   dans cette colonne.
2. **Un registre** — `ReturnIncident`. Le check-in comme le ramassage y
   projettent leurs quantités, si bien que tous les rapports voient les deux.
3. **Une déduction** — `etat_retour_de_la_ligne`, appelée par les trois
   écrivains, jamais réimplémentée.
"""

from __future__ import annotations

from .models import EtatRetour, ReturnIncident, ReturnIncidentType

#: Du plus grave au moins grave : sert quand une ligne ne porte qu'une nature.
ORDRE_GRAVITE = (
    ReturnIncidentType.DESTROYED,
    ReturnIncidentType.BROKEN,
    ReturnIncidentType.MISSING,
)

#: Type d'incident → état de la ligne. `DESTROYED` retombe sur « cassé » : le
#: vocabulaire de la ligne s'arrête là, la destruction se lit sur le ticket SAV.
ETAT_PAR_TYPE = {
    ReturnIncidentType.DESTROYED: EtatRetour.CASSE,
    ReturnIncidentType.BROKEN: EtatRetour.CASSE,
    ReturnIncidentType.MISSING: EtatRetour.MANQUANT,
}

#: Champ du payload de ramassage (SCRUM-112) → type d'incident. « Ramassée OK »
#: n'y figure pas : l'absence de problème ne s'enregistre pas.
CHAMPS_RAMASSAGE = (
    ("quantite_sav", ReturnIncidentType.BROKEN),
    ("quantite_detruite", ReturnIncidentType.DESTROYED),
    ("quantite_manquante", ReturnIncidentType.MISSING),
)

#: Champ du payload de check-in (SCRUM-94) → type d'incident.
CHAMPS_CHECKIN = (
    ("casse", ReturnIncidentType.BROKEN),
    ("manquant", ReturnIncidentType.MISSING),
)


def quantite_attendue_au_retour(ligne) -> int:
    """Combien d'unités doivent revenir de cette ligne.

    Quatre endroits écrivaient `quantite_livree or quantite_demandee`, chacun
    pour une raison différente : le plafond du registre d'incidents, celui de la
    saisie de ramassage, la quantité à ramasser du bon et le total de la tournée.

    Le repli sur `quantite_demandee` n'est pas une précaution : `quantite_livree`
    n'est alimentée par aucun endpoint à ce jour et vaut donc 0 partout. Le jour
    où elle le sera, la règle changera de comportement en production — d'où un
    seul endroit à corriger, et un test qui distingue les deux valeurs.
    """

    return ligne.quantite_livree or ligne.quantite_demandee or 0


def quantites_depuis_payload(payload, champs):
    """Traduit un payload d'écran en {type d'incident: quantité}."""

    return {
        type_incident: payload.get(champ, 0) or 0 for champ, type_incident in champs
    }


def quantites_du_retour(ligne) -> dict:
    """Reconstitue les quantités d'un retour depuis le registre.

    Ces chiffres étaient stockés en double sur la ligne — une colonne par écran,
    sept en tout — alors qu'ils se déduisent du registre et de la seule quantité
    qui ne s'en déduit pas : combien est revenu physiquement.

    `ok` = revenu physiquement moins ce qui est revenu abîmé ou détruit.
    """

    par_type = dict.fromkeys(ReturnIncidentType.values, 0)

    for type_incident, qty in ligne.incidents.values_list("type", "qty"):
        par_type[type_incident] = par_type.get(type_incident, 0) + (qty or 0)

    revenue = ligne.quantite_retournee or 0
    abimee = (
        par_type[ReturnIncidentType.BROKEN] + par_type[ReturnIncidentType.DESTROYED]
    )

    return {
        "revenue": revenue,
        "ok": max(revenue - abimee, 0),
        "casse": par_type[ReturnIncidentType.BROKEN],
        "detruit": par_type[ReturnIncidentType.DESTROYED],
        "manquant": par_type[ReturnIncidentType.MISSING],
    }


def facturer_le_client(ligne) -> bool:
    """Vrai si au moins un incident de la ligne est refacturé au client."""

    return ligne.incidents.filter(bill_client=True).exists()


def projeter_incidents(ligne, user, quantites, *, facturer=None) -> None:
    """Projette les quantités saisies par un écran dans le registre.

    `quantites` associe un type d'incident à sa quantité. Les écrans passent ce
    qu'ils ont reçu : plus aucune colonne de la ligne n'est lue, elles n'existent
    plus (cf. migration 0021).

    Idempotent : ré-enregistrer ajuste les quantités, et une quantité ramenée à
    0 supprime l'incident correspondant — un incident n'a pas de cycle de vie
    propre, contrairement au ticket SAV qu'on clôture pour garder la trace.

    `facturer` vaut la décision commerciale de l'écran appelant, ou None quand
    il n'en prend pas (le check-in ne facture rien) : dans ce cas le drapeau
    déjà posé sur l'incident est conservé.
    """

    for type_incident, quantite in quantites.items():
        quantite = quantite or 0
        incident = ReturnIncident.objects.filter(
            line=ligne,
            type=type_incident,
        ).first()

        if quantite <= 0:
            if incident is not None:
                incident.delete()

            continue

        if incident is None:
            ReturnIncident.objects.create(
                line=ligne,
                type=type_incident,
                qty=quantite,
                comment=ligne.commentaire,
                bill_client=bool(facturer),
                reported_by=user,
            )

            continue

        incident.qty = quantite
        incident.comment = ligne.commentaire or incident.comment

        if facturer is not None:
            incident.bill_client = facturer

        incident.save()


def etat_retour_du_pointage(ligne) -> str:
    """État d'une ligne sans incident : pointée et conforme, ou pas pointée.

    Toutes les natures de problème vivent dans le registre ; s'il est vide, il
    ne reste qu'une question — quelqu'un a-t-il regardé cette ligne. La réponse
    est `quantite_retournee`, seule colonne de retour conservée : « combien est
    revenu physiquement ».

    Le repli sert aussi à ne pas effacer un pointage quand le dernier incident
    d'une ligne est supprimé.
    """

    if (ligne.quantite_retournee or 0) > 0:
        return EtatRetour.OK

    return ""


def etat_retour_de_la_ligne(ligne) -> str:
    """L'état d'une ligne, déduit du registre puis du pointage.

    Recalculé et non mémorisé au fil de l'eau : modifier ou supprimer un
    incident doit ramener la ligne à son état réel, sinon elle reste figée sur
    un incident qui n'existe plus.

    Quand plusieurs natures coexistent, la plus grave l'emporte (`ORDRE_GRAVITE`).
    """

    types = set(ligne.incidents.values_list("type", flat=True))

    for type_incident in ORDRE_GRAVITE:
        if type_incident in types:
            return ETAT_PAR_TYPE[type_incident]

    return etat_retour_du_pointage(ligne)


def appliquer_etat_retour(ligne, *, save: bool = True) -> str:
    """Recalcule `etat_retour` et l'écrit (sauf `save=False`)."""

    ligne.etat_retour = etat_retour_de_la_ligne(ligne)

    if save:
        ligne.save(update_fields=["etat_retour", "updated_at"])

    return ligne.etat_retour
