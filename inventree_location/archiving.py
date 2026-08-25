"""Archivage des réservations terminées (SCRUM-101).

Une réservation close depuis plus de deux ans sort de la liste par défaut
sans être supprimée : elle reste consultable via `?include_archived=true`.
"""

from datetime import timedelta

from django.utils import timezone

from .models import Reservation, StatutReservation

ARCHIVABLE_STATUSES = (
    StatutReservation.CLOTUREE,
    StatutReservation.ANNULEE,
    StatutReservation.REFUSEE,
)

ARCHIVE_AFTER_DAYS = 365 * 2


def get_archivable_queryset(now=None):
    """Réservations closes dont la demande date de plus de deux ans."""

    now = now or timezone.now()
    cutoff = now - timedelta(days=ARCHIVE_AFTER_DAYS)

    return Reservation.objects.filter(
        statut__in=ARCHIVABLE_STATUSES,
        is_archived=False,
        date_demande__lt=cutoff,
    )


def archive_old_reservations(now=None):
    """Marque les réservations archivables et retourne leur nombre.

    `updated_at` est posé explicitement : un `queryset.update()` court-circuite
    `auto_now`, et l'archivage serait passé sans laisser de trace de date.
    """

    queryset = get_archivable_queryset(now=now)

    return queryset.update(is_archived=True, updated_at=timezone.now())
