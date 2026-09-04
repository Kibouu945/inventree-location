"""Calendrier des réservations (DIS-01).

Traduit les réservations en évènements FullCalendar. La palette vit ici, côté
serveur : la légende de l'écran et les pastilles du calendrier viennent alors
de la même source, et un statut ajouté au modèle ne peut pas se retrouver sans
couleur dans un coin de code React.
"""

from __future__ import annotations

from django.db.models.functions import Coalesce

from . import roles
from .models import Reservation, StatutReservation

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


def couleur_statut(statut: str) -> str:
    """Couleur associée à ce statut."""

    return STATUT_COULEURS.get(statut, COULEUR_DEFAUT)


def reservations_du_calendrier(user, *, debut=None, fin=None):
    """Réservations à afficher entre ces deux bornes.

    Une réservation sans dates de retrait / retour (brouillon) retombe sur les
    dates de sa prestation : sinon elle n'apparaîtrait nulle part alors que
    l'écran sert précisément à repérer ce qui est mal renseigné.
    """

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

    return [
        evenement(reservation)
        for reservation in reservations_du_calendrier(user, debut=debut, fin=fin)
    ]
