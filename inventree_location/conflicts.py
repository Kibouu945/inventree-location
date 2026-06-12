from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, List, Optional, Sequence, TypeVar, Union

DateOrDateTime = Union[date, datetime]

CONFLICT_STATUSES = {"confirmée", "livrée", "retournée"}

T = TypeVar("T")


@dataclass(frozen=True)
class ReservationRecord:
    """Representation minimale d'une réservation pour la détection de conflits."""

    id: int
    part_id: int
    qty: int
    start: DateOrDateTime
    end: DateOrDateTime
    status: str


def periods_overlap(
    start_a: DateOrDateTime,
    end_a: DateOrDateTime,
    start_b: DateOrDateTime,
    end_b: DateOrDateTime,
) -> bool:
    """Return True when two booking intervals overlap.

    Intervals are considered inclusive at both ends.
    """
    return start_a <= end_b and end_a >= start_b


def filter_conflict_statuses(reservations: Iterable[ReservationRecord]) -> List[ReservationRecord]:
    """Return only reservations whose status must be checked for conflicts."""
    return [r for r in reservations if r.status in CONFLICT_STATUSES]


def find_conflicting_reservations(
    reservations: Iterable[ReservationRecord],
    part_id: int,
    start: DateOrDateTime,
    end: DateOrDateTime,
    exclude_resa_id: Optional[int] = None,
) -> List[ReservationRecord]:
    """Return reservations that overlap the given period for the same part.

    This helper is intentionally decoupled from any database model.
    """
    conflicts: List[ReservationRecord] = []

    for reservation in filter_conflict_statuses(reservations):
        if reservation.part_id != part_id:
            continue

        if exclude_resa_id is not None and reservation.id == exclude_resa_id:
            continue

        if periods_overlap(start, end, reservation.start, reservation.end):
            conflicts.append(reservation)

    return conflicts


def compute_conflicts(
    part_id: int,
    qty: int,
    start: DateOrDateTime,
    end: DateOrDateTime,
    exclude_resa_id: Optional[int] = None,
) -> List:
    """Compute the list of conflicting reservations for a part and a period.

    Règles de conflit :
    - mêmes `part_id`
    - statut dans `confirmée`, `livrée`, `retournée`
    - périodes qui se chevauchent ou se touchent aux bornes
    - permet d'exclure la réservation en cours via `exclude_resa_id`

    Le paramètre `qty` est conservé dans la signature pour la logique de ressources et de quantité;
    la détection retourne aujourd'hui la liste des réservations temporellement conflictuelles.
    """
    if start > end:
        raise ValueError("La date de début doit être antérieure ou égale à la date de fin.")

    try:
        from .models import Reservation  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "No Reservation model is defined in inventree_location.models"
        ) from exc

    active_reservations = Reservation.objects.filter(
        part_id=part_id,
        status__in=CONFLICT_STATUSES,
    ).exclude(pk=exclude_resa_id)

    return [
        reservation
        for reservation in active_reservations
        if periods_overlap(start, end, reservation.start, reservation.end)
    ]
