from datetime import date

from inventree_location.conflicts import (
    CONFLICT_STATUSES,
    ReservationRecord,
    find_conflicting_reservations,
    periods_overlap,
)


def test_periods_overlap_inclusive_endpoints():
    assert periods_overlap(date(2026, 6, 10), date(2026, 6, 15), date(2026, 6, 15), date(2026, 6, 20))
    assert periods_overlap(date(2026, 6, 15), date(2026, 6, 20), date(2026, 6, 10), date(2026, 6, 15))


def test_find_conflicting_reservations_returns_overlap():
    reservations = [
        ReservationRecord(id=1, part_id=1, qty=2, start=date(2026, 6, 5), end=date(2026, 6, 12), status="confirmée"),
        ReservationRecord(id=2, part_id=1, qty=1, start=date(2026, 6, 20), end=date(2026, 6, 25), status="confirmée"),
    ]

    conflicts = find_conflicting_reservations(
        reservations,
        part_id=1,
        start=date(2026, 6, 10),
        end=date(2026, 6, 18),
    )

    assert len(conflicts) == 1
    assert conflicts[0].id == 1


def test_find_conflicting_reservations_ignores_other_part():
    reservations = [
        ReservationRecord(id=1, part_id=2, qty=2, start=date(2026, 6, 10), end=date(2026, 6, 18), status="confirmée"),
    ]

    conflicts = find_conflicting_reservations(
        reservations,
        part_id=1,
        start=date(2026, 6, 10),
        end=date(2026, 6, 18),
    )

    assert conflicts == []


def test_find_conflicting_reservations_ignores_excluded_reservation():
    reservations = [
        ReservationRecord(id=1, part_id=1, qty=2, start=date(2026, 6, 10), end=date(2026, 6, 18), status="confirmée"),
    ]

    conflicts = find_conflicting_reservations(
        reservations,
        part_id=1,
        start=date(2026, 6, 10),
        end=date(2026, 6, 18),
        exclude_resa_id=1,
    )

    assert conflicts == []


def test_find_conflicting_reservations_ignores_non_conflict_status():
    assert "draft" not in CONFLICT_STATUSES

    reservations = [
        ReservationRecord(id=1, part_id=1, qty=2, start=date(2026, 6, 10), end=date(2026, 6, 18), status="draft"),
    ]

    conflicts = find_conflicting_reservations(
        reservations,
        part_id=1,
        start=date(2026, 6, 10),
        end=date(2026, 6, 18),
    )

    assert conflicts == []


def test_find_conflicting_reservations_returns_multiple_overlaps():
    reservations = [
        ReservationRecord(id=1, part_id=1, qty=2, start=date(2026, 6, 10), end=date(2026, 6, 15), status="confirmée"),
        ReservationRecord(id=2, part_id=1, qty=1, start=date(2026, 6, 12), end=date(2026, 6, 18), status="livrée"),
        ReservationRecord(id=3, part_id=1, qty=1, start=date(2026, 6, 20), end=date(2026, 6, 25), status="retournée"),
    ]

    conflicts = find_conflicting_reservations(
        reservations,
        part_id=1,
        start=date(2026, 6, 14),
        end=date(2026, 6, 22),
    )

    assert [r.id for r in conflicts] == [1, 2, 3]
