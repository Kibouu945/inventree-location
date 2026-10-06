"""Service métier pour gérer le workflow de statut des réservations."""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from inventree_location.conflicts import (
    detect_reservation_conflicts,
    message_de_refus,
    verrouiller_les_articles,
)
from inventree_location.execution import projeter_le_bon
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
        raise serializers.ValidationError({
            "detail": "La réservation possède déjà ce statut.",
            "current_status": old_status,
        })

    if new_status not in available_transitions:
        raise serializers.ValidationError({
            "detail": "Transition de statut invalide.",
            "current_status": old_status,
            "requested_status": new_status,
            "available_transitions": available_transitions,
        })

    # Le contrôle de stock, le statut, sa trace et sa projection : une seule
    # transaction, pour que le verrou tienne jusqu'à l'enregistrement.
    with transaction.atomic():
        # Valider une réservation en conflit non forcé est refusé (forced passe).
        if new_status == StatutReservation.VALIDEE and not reservation.forced:
            verrouiller_les_articles(reservation)
            conflict_result = detect_reservation_conflicts(reservation)

            if conflict_result["has_conflict"]:
                raise serializers.ValidationError({
                    "detail": message_de_refus(conflict_result),
                    "conflicts": conflict_result["conflicts"],
                })

        reservation.statut = new_status

        if new_status == StatutReservation.VALIDEE and user is not None:
            reservation.validateur = user

        colonnes = ["statut", "validateur", "updated_at"]

        # L'heure réelle du dépôt, sur ce chemin aussi.
        if (
            new_status == StatutReservation.LIVREE
            and reservation.date_retrait_reelle is None
        ):
            reservation.date_retrait_reelle = timezone.now()
            colonnes.append("date_retrait_reelle")

        reservation.save(update_fields=colonnes)

        log = ReservationStatusLog.objects.create(
            reservation=reservation,
            changed_by=user if getattr(user, "is_authenticated", False) else None,
            from_status=old_status,
            to_status=new_status,
            comment=comment,
        )

        projeter_le_bon(reservation)

    return {
        "reservation": reservation.pk,
        "old_status": old_status,
        "new_status": new_status,
        "changed_by": log.changed_by_id,
        "changed_at": log.created_at,
        "comment": log.comment,
        "available_transitions": get_available_transitions(new_status),
    }
