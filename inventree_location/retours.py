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

#: Quantités de la saisie de ramassage (SCRUM-112) → types d'incident.
#: « Ramassée OK » ne produit aucun incident : c'est l'absence de problème.
INCIDENTS_RAMASSAGE = (
    ("quantite_sav", ReturnIncidentType.BROKEN),
    ("quantite_detruite", ReturnIncidentType.DESTROYED),
    ("quantite_manquante", ReturnIncidentType.MISSING),
)

#: Quantités du check-in retour (SCRUM-94) → types d'incident.
INCIDENTS_CHECKIN = (
    ("quantite_retour_casse", ReturnIncidentType.BROKEN),
    ("quantite_retour_manquant", ReturnIncidentType.MISSING),
)


def projeter_incidents(ligne, user, mapping, *, facturer=None) -> None:
    """Projette les quantités d'un écran dans le registre d'incidents.

    Idempotent : ré-enregistrer ajuste les quantités, et une quantité ramenée à
    0 supprime l'incident correspondant — un incident n'a pas de cycle de vie
    propre, contrairement au ticket SAV qu'on clôture pour garder la trace.

    `facturer` vaut la décision commerciale de l'écran appelant, ou None quand
    il n'en prend pas (le check-in ne facture rien) : dans ce cas le drapeau
    déjà posé sur l'incident est conservé.
    """

    for champ, type_incident in mapping:
        quantite = getattr(ligne, champ, 0) or 0
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


#: Colonnes qui, à elles seules, signent une nature de problème. Utile pour les
#: lignes écrites avant l'unification, qui n'ont pas d'incident associé.
NATURES_DU_POINTAGE = (
    (("quantite_retour_casse", "quantite_sav", "quantite_detruite"), EtatRetour.CASSE),
    (("quantite_retour_manquant", "quantite_manquante"), EtatRetour.MANQUANT),
)

#: Toutes les colonnes de pointage, les deux écrans confondus : leur somme dit
#: si quelqu'un a regardé la ligne.
COLONNES_DE_POINTAGE = (
    "quantite_retour_ok",
    "quantite_retour_manquant",
    "quantite_retour_casse",
    "quantite_ramassee",
    "quantite_sav",
    "quantite_detruite",
    "quantite_manquante",
)


def etat_retour_du_pointage(ligne) -> str:
    """État déduit des colonnes, quand la ligne ne porte aucun incident.

    Deux écrans pointent la même ligne dans deux familles de colonnes — le
    check-in (`quantite_retour_*`) et le ramassage (`quantite_ramassee` et
    consorts). La déduction de repli lisait la première seulement : un
    ramassage entièrement conforme retombait donc sur « pas encore pointé »
    alors qu'il venait d'être saisi.

    Le repli sert à deux choses : ne pas effacer un pointage quand le dernier
    incident d'une ligne est supprimé, et rester juste sur les lignes écrites
    avant l'unification, qui n'ont pas d'incident associé.
    """

    for champs, etat in NATURES_DU_POINTAGE:
        if any((getattr(ligne, champ, 0) or 0) > 0 for champ in champs):
            return etat

    pointe = sum((getattr(ligne, champ, 0) or 0) for champ in COLONNES_DE_POINTAGE)

    if pointe <= 0:
        return ""

    # Pointé, et aucune nature de problème : tout est rentré en état.
    return EtatRetour.OK


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
