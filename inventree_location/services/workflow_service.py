"""Service métier pour gérer le workflow de statut des réservations.

**Deuxième point d'écriture des tables d'exécution (lot L7).** Les six
appelants de `transition_reservation_status` — le bouton « livrer » du
gestionnaire, l'arbitrage de statut, le retour complet, le check-in retour,
l'annulation d'une manifestation et le journal du livreur — passent tous par
ici : greffer la projection sur le service plutôt que sur chacun d'eux, c'est
une seule écriture au lieu de six, et aucun appelant futur à ne pas oublier.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from inventree_location.conflicts import detect_reservation_conflicts
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

    # Valider une réservation en conflit non forcé est refusé (forced passe).
    if new_status == StatutReservation.VALIDEE and not reservation.forced:
        conflict_result = detect_reservation_conflicts(reservation)

        if conflict_result["has_conflict"]:
            raise serializers.ValidationError({
                "detail": (
                    "Validation refusée : conflit de stock détecté. "
                    "Résolvez le conflit ou passez forced=true."
                ),
                "conflicts": conflict_result["conflicts"],
            })

    reservation.statut = new_status

    if new_status == StatutReservation.VALIDEE and user is not None:
        reservation.validateur = user

    colonnes = ["statut", "validateur", "updated_at"]

    # L'heure réelle du dépôt, sur ce chemin aussi. Le journal du livreur
    # l'écrit de son côté, mais un bon livré par le bouton « Marquer livrée »
    # n'y passe pas : son passage restait sans heure, et la vérification ne le
    # voyait pas — elle ne comparait pas les dates. Vu en recette navigateur le
    # 17/09/2026.
    if (
        new_status == StatutReservation.LIVREE
        and reservation.date_retrait_reelle is None
    ):
        reservation.date_retrait_reelle = timezone.now()
        colonnes.append("date_retrait_reelle")

    # Le statut, sa trace et sa projection : une seule transaction. Une table
    # d'exécution qui survivrait à un statut annulé serait précisément la
    # divergence que le lot L6 s'est donné les moyens de détecter. `atomic`
    # s'imbrique en point de sauvegarde quand l'appelant en ouvre déjà une.
    with transaction.atomic():
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
