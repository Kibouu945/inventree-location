from datetime import date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from inventree_location.conflicts import (
    ReservationRecord,
    compute_conflicts,
    find_conflicting_reservations,
)
from inventree_location.models import (
    LigneReservation,
    Prestation,
    Reservation,
)
from inventree_location.tests.factories import make_manifestation


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


# ---------------------------------------------------------------------------
# Tests DB de compute_conflicts (CON-01)
#
# compute_conflicts interroge la base réelle ; ces tests garantissent que la
# requête ORM cible le bon champ (lignes__part) et détecte les chevauchements.
# ---------------------------------------------------------------------------


def _make_reservation(prestation, user, part, *, statut, start, end):
    reservation = Reservation.objects.create(
        prestation=prestation,
        demandeur=user,
        date_demande=timezone.now(),
        statut=statut,
        date_retrait_prevue=start,
        date_retour_prevue=end,
    )
    LigneReservation.objects.create(
        reservation=reservation, part=part, quantite_demandee=1
    )
    return reservation


@pytest.fixture
def conflict_setup(db):
    from part.models import Part

    user = get_user_model().objects.create_user(username="bob", password="pwd12345")
    now = timezone.now().replace(microsecond=0)
    manifestation = make_manifestation(
        nom="Camp",
        date_debut=now,
        date_fin=now,
    )
    prestation = Prestation.objects.create(
        manifestation=manifestation, nom="P", date_debut=now, date_fin=now
    )
    part = Part.objects.create(name="Tente")
    other_part = Part.objects.create(name="Réchaud")
    return {
        "user": user,
        "prestation": prestation,
        "part": part,
        "other_part": other_part,
        "now": now,
    }


@pytest.mark.django_db
def test_compute_conflicts_detects_overlap(conflict_setup):
    now = conflict_setup["now"]
    resa = _make_reservation(
        conflict_setup["prestation"],
        conflict_setup["user"],
        conflict_setup["part"],
        statut="validee",
        start=now,
        end=now + timedelta(days=2),
    )

    conflicts = compute_conflicts(
        conflict_setup["part"].pk,
        1,
        now + timedelta(days=1),
        now + timedelta(days=3),
    )

    assert [r.pk for r in conflicts] == [resa.pk]


@pytest.mark.django_db
def test_compute_conflicts_ignores_other_part_and_excluded(conflict_setup):
    now = conflict_setup["now"]
    resa = _make_reservation(
        conflict_setup["prestation"],
        conflict_setup["user"],
        conflict_setup["part"],
        statut="validee",
        start=now,
        end=now + timedelta(days=2),
    )
    # Autre part : ne doit pas remonter.
    _make_reservation(
        conflict_setup["prestation"],
        conflict_setup["user"],
        conflict_setup["other_part"],
        statut="validee",
        start=now,
        end=now + timedelta(days=2),
    )

    # Sans exclusion : la résa du bon part remonte.
    assert [
        r.pk for r in compute_conflicts(conflict_setup["part"].pk, 1, now, now)
    ] == [resa.pk]

    # En excluant la résa, plus aucun conflit.
    assert (
        compute_conflicts(
            conflict_setup["part"].pk, 1, now, now, exclude_resa_id=resa.pk
        )
        == []
    )
