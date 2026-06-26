from datetime import date, datetime

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


def test_periods_overlap_touching_boundaries_conflict():
    reservation = ReservationRecord(
        id=4,
        part_id=1,
        qty=1,
        start=date(2026, 6, 5),
        end=date(2026, 6, 10),
        status="confirmée",
    )

    conflicts = find_conflicting_reservations(
        [reservation],
        part_id=1,
        start=date(2026, 6, 10),
        end=date(2026, 6, 12),
    )

    assert conflicts == [reservation]


def test_existing_reservation_within_candidate_conflict():
    reservation = ReservationRecord(
        id=5,
        part_id=1,
        qty=1,
        start=date(2026, 6, 10),
        end=date(2026, 6, 12),
        status="livrée",
    )

    conflicts = find_conflicting_reservations(
        [reservation],
        part_id=1,
        start=date(2026, 6, 8),
        end=date(2026, 6, 14),
    )

    assert conflicts == [reservation]


def test_candidate_within_existing_reservation_conflict():
    reservation = ReservationRecord(
        id=6,
        part_id=1,
        qty=1,
        start=date(2026, 6, 8),
        end=date(2026, 6, 20),
        status="retournée",
    )

    conflicts = find_conflicting_reservations(
        [reservation],
        part_id=1,
        start=date(2026, 6, 10),
        end=date(2026, 6, 12),
    )

    assert conflicts == [reservation]


def test_different_part_id_no_conflict():
    reservation = ReservationRecord(
        id=7,
        part_id=2,
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

    assert conflicts == []


def test_non_conflicting_status_ignored():
    reservation = ReservationRecord(
        id=8,
        part_id=1,
        qty=1,
        start=date(2026, 6, 10),
        end=date(2026, 6, 15),
        status="brouillon",
    )

    conflicts = find_conflicting_reservations(
        [reservation],
        part_id=1,
        start=date(2026, 6, 12),
        end=date(2026, 6, 18),
    )

    assert conflicts == []


def test_datetime_inputs_overlap():
    reservation = ReservationRecord(
        id=9,
        part_id=1,
        qty=1,
        start=datetime(2026, 6, 10, 14, 0),
        end=datetime(2026, 6, 15, 10, 0),
        status="confirmée",
    )

    conflicts = find_conflicting_reservations(
        [reservation],
        part_id=1,
        start=datetime(2026, 6, 15, 0, 0),
        end=datetime(2026, 6, 16, 0, 0),
    )

    assert conflicts == [reservation]


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
