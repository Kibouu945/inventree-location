"""État d'un retour : un vocabulaire, un registre, une déduction."""

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
    """Combien d'unités doivent revenir de cette ligne."""

    return ligne.quantite_livree or ligne.quantite_demandee or 0


def quantites_depuis_payload(payload, champs):
    """Traduit un payload d'écran en {type d'incident: quantité}."""

    return {
        type_incident: payload.get(champ, 0) or 0 for champ, type_incident in champs
    }


def quantites_du_retour(ligne) -> dict:
    """Reconstitue les quantités d'un retour depuis le registre."""

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
    """Projette les quantités saisies par un écran dans le registre."""

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
    """État d'une ligne sans incident : pointée et conforme, ou pas pointée."""

    if (ligne.quantite_retournee or 0) > 0:
        return EtatRetour.OK

    return ""


def etat_retour_de_la_ligne(ligne) -> str:
    """L'état d'une ligne, déduit du registre puis du pointage."""

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
