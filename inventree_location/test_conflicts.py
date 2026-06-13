from datetime import date

from inventree_location.conflicts import (
    ReservationRecord,
    compute_conflicts,
    find_conflicting_reservations,
)


def test_periods_overlap_conflict():
    reservation = ReservationRecord(
        id=1,
        part_id=1,
        qty=1,
        start=date(2026, 6, 10),
        end=date(2026, 6, 15),
        status="confirmée",
    )

    conflicts = find_conflicting_reservations(
        [reservation],
        part_id=1,
        start=date(2026, 6, 12),
        end=date(2026, 6, 18),
    )

    assert conflicts == [reservation]


def test_periods_do_not_conflict():
    reservation = ReservationRecord(
        id=2,
        part_id=1,
        qty=1,
        start=date(2026, 6, 1),
        end=date(2026, 6, 5),
        status="confirmée",
    )

    conflicts = find_conflicting_reservations(
        [reservation],
        part_id=1,
        start=date(2026, 6, 6),
        end=date(2026, 6, 9),
    )

    assert conflicts == []


def test_exclude_reservation():
    reservation = ReservationRecord(
        id=3,
        part_id=1,
        qty=1,
        start=date(2026, 6, 10),
        end=date(2026, 6, 20),
        status="livrée",
    )

    conflicts = find_conflicting_reservations(
        [reservation],
        part_id=1,
        start=date(2026, 6, 12),
        end=date(2026, 6, 18),
        exclude_resa_id=3,
    )

    assert conflicts == []


def test_compute_conflicts_requires_valid_period():
    try:
        compute_conflicts(1, 1, date(2026, 6, 20), date(2026, 6, 10))
    except ValueError as exc:
        assert str(exc) == "start must be before or equal to end"
    else:
        assert False, "ValueError not raised"
