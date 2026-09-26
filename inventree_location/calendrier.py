"""Calendrier des réservations (DIS-01)."""

from __future__ import annotations

from django.db.models.functions import Coalesce
from django.utils.dateparse import parse_date, parse_datetime

from . import roles
from .models import Reservation, StatutReservation

#: Fenêtre maximale acceptée, en jours.
MAX_FENETRE_JOURS = 92

#: Au-delà, on refuse plutôt que de tronquer en silence.
MAX_EVENEMENTS = 1000

#: Couleur d'un évènement par statut de réservation.
STATUT_COULEURS: dict[str, str] = {
    StatutReservation.BROUILLON: "#868e96",
    StatutReservation.SOUMISE: "#228be6",
    StatutReservation.VALIDEE: "#40c057",
    StatutReservation.REFUSEE: "#fa5252",
    StatutReservation.ANNULEE: "#e8590c",
    StatutReservation.LIVREE: "#12b886",
    StatutReservation.RETOURNEE: "#be4bdb",
    StatutReservation.CLOTUREE: "#343a40",
}

#: Couleur de repli pour un statut inconnu de la palette.
COULEUR_DEFAUT = "#868e96"


class FenetreInvalide(Exception):
    """Fenêtre de calendrier refusée, porteuse du message à afficher."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def couleur_statut(statut: str) -> str:
    """Couleur associée à ce statut."""

    return STATUT_COULEURS.get(statut, COULEUR_DEFAUT)


def _jour(valeur: str, nom: str):
    """Lit une borne, qu'elle soit un jour ou un horodatage complet."""

    valeur = valeur.strip()
    horodatage = parse_datetime(valeur)

    if horodatage is not None:
        return horodatage.date()

    jour = parse_date(valeur)

    if jour is None:
        raise FenetreInvalide(
            f"Le paramètre « {nom} » n'est pas une date lisible : « {valeur} »."
        )

    return jour


def bornes_fenetre(depuis: str | None, jusqua: str | None):
    """Valide la fenêtre demandée et retourne ses deux jours."""

    if not depuis or not jusqua:
        raise FenetreInvalide(
            "Le calendrier demande une période : renseignez « from » et « to »."
        )

    debut = _jour(depuis, "from")
    fin = _jour(jusqua, "to")

    if fin < debut:
        raise FenetreInvalide("La fin de la période précède son début.")

    if (fin - debut).days > MAX_FENETRE_JOURS:
        raise FenetreInvalide(
            f"Période trop large : {MAX_FENETRE_JOURS} jours au maximum."
        )

    return debut, fin


def reservations_du_calendrier(user, *, debut=None, fin=None):
    """Réservations à afficher entre ces deux bornes."""

    queryset = (
        Reservation.objects.select_related(
            "prestation",
            "prestation__lieu",
            "prestation__manifestation",
            "demandeur",
        )
        .filter(is_archived=False)
        .annotate(
            debut_calendrier=Coalesce("date_retrait_prevue", "prestation__date_debut"),
            fin_calendrier=Coalesce("date_retour_prevue", "prestation__date_fin"),
        )
    )

    # Un livreur pur ne voit que les réservations validées, comme partout
    # ailleurs (cf. `roles.py`).
    if roles.sees_only_deliverable_reservations(user):
        queryset = queryset.filter(statut=StatutReservation.VALIDEE)

    if debut is not None:
        queryset = queryset.filter(**debut)

    if fin is not None:
        queryset = queryset.filter(**fin)

    return queryset.order_by("debut_calendrier")


def evenement(reservation) -> dict:
    """Un évènement FullCalendar pour cette réservation."""

    prestation = reservation.prestation
    lieu = prestation.lieu if prestation_a_un_lieu(prestation) else None

    return {
        "id": str(reservation.pk),
        "title": f"{reservation.numero} — {prestation.nom}",
        "start": _iso(reservation.debut_calendrier),
        "end": _iso(reservation.fin_calendrier),
        "color": couleur_statut(reservation.statut),
        "extendedProps": {
            "reservation": reservation.pk,
            "numero": reservation.numero,
            "statut": reservation.get_statut_display(),
            "statut_code": reservation.statut,
            "prestation": prestation.nom,
            "manifestation": prestation.manifestation.nom,
            "lieu": lieu.nom if lieu else "",
            "demandeur": _nom(reservation.demandeur),
        },
    }


def prestation_a_un_lieu(prestation) -> bool:
    """Vrai si la prestation porte un lieu (nullable sur un brouillon)."""

    return getattr(prestation, "lieu_id", None) is not None


def _iso(valeur):
    """Date ISO, ou `None` si la réservation n'a aucune date exploitable."""

    return valeur.isoformat() if valeur is not None else None


def _nom(user) -> str:
    """Nom lisible d'un utilisateur."""

    if user is None:
        return ""

    complet = f"{user.first_name} {user.last_name}".strip()

    return complet or user.username


def evenements_calendrier(user, *, debut=None, fin=None) -> list[dict]:
    """Liste d'évènements FullCalendar pour la période demandée."""

    queryset = reservations_du_calendrier(user, debut=debut, fin=fin)
    reservations = list(queryset[: MAX_EVENEMENTS + 1])

    if len(reservations) > MAX_EVENEMENTS:
        raise FenetreInvalide(
            f"Plus de {MAX_EVENEMENTS} réservations sur cette période : "
            "resserrez la fenêtre."
        )

    return [evenement(reservation) for reservation in reservations]
