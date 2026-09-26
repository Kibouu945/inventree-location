"""Archivage des réservations terminées (SCRUM-101)."""

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
    """Marque les réservations archivables et retourne leur nombre."""

    queryset = get_archivable_queryset(now=now)

    return queryset.update(is_archived=True, updated_at=timezone.now())
