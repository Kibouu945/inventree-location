"""Service métier pour gérer le workflow de statut des réservations."""

from rest_framework import serializers

from inventree_location.models import (
    ReservationStatusLog,
    StatutReservation,
)


VALID_TRANSITIONS = {
    StatutReservation.BROUILLON: [
        StatutReservation.VALIDEE,
        StatutReservation.ANNULEE,
    ],
    StatutReservation.SOUMISE: [
        StatutReservation.VALIDEE,
        StatutReservation.REFUSEE,
        StatutReservation.ANNULEE,
    ],
    StatutReservation.VALIDEE: [
        StatutReservation.LIVREE,
        StatutReservation.ANNULEE,
    ],
    StatutReservation.LIVREE: [
        StatutReservation.RETOURNEE,
        StatutReservation.ANNULEE,
    ],
    StatutReservation.RETOURNEE: [
        StatutReservation.CLOTUREE,
        StatutReservation.ANNULEE,
    ],
    StatutReservation.CLOTUREE: [],
    StatutReservation.REFUSEE: [],
    StatutReservation.ANNULEE: [],
}


def get_available_transitions(current_status):
    """Retourne les transitions possibles depuis un statut donné."""

    return VALID_TRANSITIONS.get(current_status, [])


def transition_reservation_status(reservation, new_status, user=None, comment=""):
    """Change le statut d'une réservation si la transition est autorisée."""

    old_status = reservation.statut
    available_transitions = get_available_transitions(old_status)

    if new_status == old_status:
        raise serializers.ValidationError(
            {
                "detail": "La réservation possède déjà ce statut.",
                "current_status": old_status,
            }
        )

    if new_status not in available_transitions:
        raise serializers.ValidationError(
            {
                "detail": "Transition de statut invalide.",
                "current_status": old_status,
                "requested_status": new_status,
                "available_transitions": available_transitions,
            }
        )

    reservation.statut = new_status

    if new_status == StatutReservation.VALIDEE and user is not None:
        reservation.validateur = user

    reservation.save(update_fields=["statut", "validateur", "updated_at"])

    log = ReservationStatusLog.objects.create(
        reservation=reservation,
        changed_by=user if getattr(user, "is_authenticated", False) else None,
        from_status=old_status,
        to_status=new_status,
        comment=comment,
    )

    return {
        "reservation": reservation.pk,
        "old_status": old_status,
        "new_status": new_status,
        "changed_by": log.changed_by_id,
        "changed_at": log.created_at,
        "comment": log.comment,
        "available_transitions": get_available_transitions(new_status),
    }
