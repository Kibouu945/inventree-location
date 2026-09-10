"""Tests du calcul de stock disponible au jour entier (STK-01)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from inventree_location.models import (
    LignePrestation,
    LigneReservation,
    Lieu,
    Prestation,
    RentableItem,
    Reservation,
    StatutReservation,
)
from inventree_location.tests.factories import (
    make_manifestation,
    mettre_en_stock,
)
from inventree_location.stock import (
    compute_engaged_quantities,
    compute_engagement_details,
    compute_parts_availability,
    compute_prestation_stock,
    compute_stock_availability,
    day_ranges_overlap,
)

User = get_user_model()


@pytest.fixture
def base(db):
    # Heure locale, pas UTC : la disponibilité « du jour » se calcule dans le
    # fuseau métier, et une fixture en UTC désignait la veille en soirée.
    now = timezone.localtime().replace(hour=8, minute=0, second=0, microsecond=0)
    user = User.objects.create_user(username="bob", password="pwd12345")
    manifestation = make_manifestation(
        nom="Camp",
        date_debut=now,
        date_fin=now + timedelta(days=10),
    )
    lieu = Lieu.objects.create(nom="Terrain")
    return {
        "now": now,
        "user": user,
        "manifestation": manifestation,
        "lieu": lieu,
    }


def _make_part(name, *, stock, virtual=False):
    from part.models import Part

    part = Part.objects.create(name=name)
    RentableItem.objects.create(part=part, is_virtual=virtual)
    mettre_en_stock(part, stock)
    return part


def _prestation(base, *, day_offset_start, hours, part=None, qty=0, nom="P"):
    now = base["now"]
    debut = now + timedelta(days=day_offset_start)
    presta = Prestation.objects.create(
        manifestation=base["manifestation"],
        lieu=base["lieu"],
        nom=nom,
        date_debut=debut,
        date_fin=debut + timedelta(hours=hours),
    )
    if part is not None:
        LignePrestation.objects.create(prestation=presta, part=part, quantite=qty)
    return presta


def _reservation(
    base,
    presta,
    part,
    qty,
    *,
    statut=StatutReservation.VALIDEE,
    day_offset_start=0,
    hours=4,
):
    """Réservation d'une prestation, avec une ligne matériel."""

    debut = base["now"] + timedelta(days=day_offset_start)
    resa = Reservation.objects.create(
        prestation=presta,
        demandeur=base["user"],
        statut=statut,
        date_retrait_prevue=debut,
        date_retour_prevue=debut + timedelta(hours=hours),
    )
    LigneReservation.objects.create(
        reservation=resa, part=part, quantite_demandee=qty
    )
    return resa


class TestDayRangesOverlap:
    def test_same_day_overlap(self):
        base_day = timezone.now().replace(hour=9)
        assert day_ranges_overlap(
            base_day,
            base_day.replace(hour=10),
            base_day.replace(hour=18),
            base_day.replace(hour=20),
        )

    def test_adjacent_days_do_not_overlap(self):
        d = timezone.now().replace(hour=9)
        assert not day_ranges_overlap(
            d,
            d.replace(hour=23),
            d + timedelta(days=1),
            d + timedelta(days=1, hours=1),
        )

    def test_iso_string_dates(self):
        assert day_ranges_overlap(
            "2026-07-01T08:00:00",
            "2026-07-03T08:00:00",
            "2026-07-02",
            "2026-07-05",
        )


@pytest.mark.django_db
class TestComputeStock:
    def test_no_shortage(self, base):
        part = _make_part("Tente", stock=10)
        result = compute_stock_availability(
            base["now"],
            base["now"] + timedelta(hours=2),
            [{"part_id": part.pk, "quantite": 4}],
        )
        assert result["has_shortage"] is False
        assert result["lines"][0]["available"] == 10

    def test_shortage_when_other_prestation_overlaps_same_day(self, base):
        part = _make_part("Chaise", stock=10)
        # Une autre prestation le même jour engage déjà 8 chaises.
        _prestation(base, day_offset_start=0, hours=3, part=part, qty=8, nom="Autre")

        result = compute_stock_availability(
            base["now"],
            base["now"] + timedelta(hours=2),
            [{"part_id": part.pk, "quantite": 5}],
        )
        assert result["has_shortage"] is True
        line = result["lines"][0]
        assert line["reserved"] == 8
        assert line["available"] == 2
        assert line["missing"] == 3

    def test_no_shortage_when_other_prestation_on_different_day(self, base):
        part = _make_part("Table", stock=10)
        # L'autre prestation est 3 jours plus tard → pas de chevauchement jour.
        _prestation(base, day_offset_start=3, hours=3, part=part, qty=9, nom="Autre")

        result = compute_stock_availability(
            base["now"],
            base["now"] + timedelta(hours=2),
            [{"part_id": part.pk, "quantite": 9}],
        )
        assert result["has_shortage"] is False
        assert result["lines"][0]["reserved"] == 0

    def test_virtual_article_ignored(self, base):
        part = _make_part("Nettoyage", stock=0, virtual=True)
        result = compute_stock_availability(
            base["now"],
            base["now"] + timedelta(hours=2),
            [{"part_id": part.pk, "quantite": 100}],
        )
        # Aucune ligne physique → pas de pénurie.
        assert result["has_shortage"] is False
        assert result["lines"] == []

    def test_compute_prestation_stock_excludes_self(self, base):
        part = _make_part("Barrière", stock=5)
        presta = _prestation(
            base, day_offset_start=0, hours=2, part=part, qty=5, nom="Cible"
        )
        # Ses propres 5 barrières ne doivent pas compter comme concurrentes.
        result = compute_prestation_stock(presta)
        assert result["has_shortage"] is False
        assert result["lines"][0]["reserved"] == 0
        assert result["lines"][0]["available"] == 5


@pytest.mark.django_db
class TestComputePartsAvailability:
    """CAT-04 : disponibilité du catalogue et du sélecteur de réservation."""

    def test_empty_part_ids_returns_empty_dict(self):
        assert compute_parts_availability([]) == {}

    def test_available_for_given_period(self, base):
        part = _make_part("Tente", stock=10)
        result = compute_parts_availability(
            [part.pk], base["now"], base["now"] + timedelta(hours=2)
        )
        assert result == {part.pk: 10}

    def test_excludes_quantity_engaged_by_overlapping_prestation(self, base):
        part = _make_part("Chaise", stock=10)
        _prestation(base, day_offset_start=0, hours=3, part=part, qty=8, nom="Autre")

        result = compute_parts_availability(
            [part.pk], base["now"], base["now"] + timedelta(hours=2)
        )
        assert result == {part.pk: 2}

    def test_defaults_to_today_when_no_period_given(self, base):
        part = _make_part("Table", stock=10)
        _prestation(base, day_offset_start=0, hours=3, part=part, qty=6, nom="Autre")

        result = compute_parts_availability([part.pk])
        assert result == {part.pk: 4}

    def test_virtual_parts_are_absent_from_result(self, base):
        part = _make_part("Nettoyage", stock=0, virtual=True)
        result = compute_parts_availability(
            [part.pk], base["now"], base["now"] + timedelta(hours=2)
        )
        assert result == {}

    def test_can_exclude_a_prestation_from_the_computation(self, base):
        part = _make_part("Barrière", stock=5)
        presta = _prestation(
            base, day_offset_start=0, hours=2, part=part, qty=5, nom="Cible"
        )

        result = compute_parts_availability(
            [part.pk],
            base["now"],
            base["now"] + timedelta(hours=2),
            exclude_prestation_id=presta.pk,
        )
        assert result == {part.pk: 5}


@pytest.mark.django_db
class TestEngagedQuantities:
    """Répartition d'un même article entre prévisionnel et réservations.

    Le prévisionnel (`LignePrestation`) et le réalisé (`LigneReservation`)
    décrivent le même besoin : on retient le plus grand des deux par
    prestation, sans double comptage ni engagement invisible.
    """

    def _period(self, base, hours=2):
        return base["now"], base["now"] + timedelta(hours=hours)

    def test_reservations_are_counted_even_without_prestation_lines(self, base):
        """Le défaut d'origine : deux réservations du même article, ignorées."""

        part = _make_part("Tente", stock=10)
        presta_a = _prestation(base, day_offset_start=0, hours=4, nom="A")
        presta_b = _prestation(base, day_offset_start=0, hours=4, nom="B")
        _reservation(base, presta_a, part, 4)
        _reservation(base, presta_b, part, 4)

        debut, fin = self._period(base)

        assert compute_engaged_quantities([part.pk], debut, fin) == {part.pk: 8}
        assert compute_parts_availability([part.pk], debut, fin) == {part.pk: 2}

    def test_non_blocking_status_is_not_counted(self, base):
        """Un brouillon ne retient rien : il n'engage pas le stock."""

        part = _make_part("Tente", stock=10)
        presta = _prestation(base, day_offset_start=0, hours=4, nom="A")
        _reservation(base, presta, part, 4, statut=StatutReservation.BROUILLON)

        debut, fin = self._period(base)

        assert compute_engaged_quantities([part.pk], debut, fin) == {}

    def test_reservation_on_another_day_is_not_counted(self, base):
        part = _make_part("Tente", stock=10)
        presta = _prestation(base, day_offset_start=3, hours=4, nom="A")
        _reservation(base, presta, part, 4, day_offset_start=3)

        debut, fin = self._period(base)

        assert compute_engaged_quantities([part.pk], debut, fin) == {}

    def test_reservation_fulfilling_its_prestation_is_not_double_counted(self, base):
        """Prestation prévoyant 6 + sa réservation de 6 → 6 engagés, pas 12."""

        part = _make_part("Chaise", stock=10)
        presta = _prestation(
            base, day_offset_start=0, hours=4, part=part, qty=6, nom="A"
        )
        _reservation(base, presta, part, 6)

        debut, fin = self._period(base)

        assert compute_engaged_quantities([part.pk], debut, fin) == {part.pk: 6}

    def test_partially_reserved_prestation_keeps_its_forecast(self, base):
        """Prévision 6, réservé 2 : la prestation retient toujours 6."""

        part = _make_part("Chaise", stock=10)
        presta = _prestation(
            base, day_offset_start=0, hours=4, part=part, qty=6, nom="A"
        )
        _reservation(base, presta, part, 2)

        debut, fin = self._period(base)

        assert compute_engaged_quantities([part.pk], debut, fin) == {part.pk: 6}

    def test_reservations_beyond_forecast_win_over_it(self, base):
        """Prévision 6, réservé 4 + 5 : c'est le réalisé (9) qui fait foi."""

        part = _make_part("Chaise", stock=20)
        presta = _prestation(
            base, day_offset_start=0, hours=4, part=part, qty=6, nom="A"
        )
        _reservation(base, presta, part, 4)
        _reservation(base, presta, part, 5)

        debut, fin = self._period(base)

        assert compute_engaged_quantities([part.pk], debut, fin) == {part.pk: 9}

    def test_engagements_of_several_prestations_add_up(self, base):
        part = _make_part("Table", stock=20)
        presta_a = _prestation(
            base, day_offset_start=0, hours=4, part=part, qty=5, nom="A"
        )
        presta_b = _prestation(base, day_offset_start=0, hours=4, nom="B")
        _reservation(base, presta_a, part, 2)  # sous le prévisionnel de A
        _reservation(base, presta_b, part, 3)

        debut, fin = self._period(base)

        assert compute_engaged_quantities([part.pk], debut, fin) == {part.pk: 8}

    def test_excluded_prestation_drops_its_lines_and_its_reservations(self, base):
        """Une prestation ne se concurrence pas elle-même, réservations comprises."""

        part = _make_part("Barrière", stock=10)
        presta = _prestation(
            base, day_offset_start=0, hours=4, part=part, qty=5, nom="Cible"
        )
        _reservation(base, presta, part, 5)

        debut, fin = self._period(base)

        assert (
            compute_engaged_quantities(
                [part.pk], debut, fin, exclude_prestation_id=presta.pk
            )
            == {}
        )

    def test_excluded_reservation_drops_its_prestation_forecast(self, base):
        """En édition, la résa ne se heurte ni à elle-même ni à sa prévision."""

        part = _make_part("Tente", stock=10)
        presta = _prestation(
            base, day_offset_start=0, hours=4, part=part, qty=6, nom="A"
        )
        resa = _reservation(base, presta, part, 6)

        debut, fin = self._period(base)

        assert (
            compute_engaged_quantities(
                [part.pk], debut, fin, exclude_reservation_id=resa.pk
            )
            == {}
        )

    def test_excluded_reservation_still_faces_its_siblings(self, base):
        """Les autres réservations de la même prestation restent opposables."""

        part = _make_part("Tente", stock=10)
        presta = _prestation(
            base, day_offset_start=0, hours=4, part=part, qty=6, nom="A"
        )
        resa = _reservation(base, presta, part, 6)
        _reservation(base, presta, part, 3)

        debut, fin = self._period(base)

        assert compute_engaged_quantities(
            [part.pk], debut, fin, exclude_reservation_id=resa.pk
        ) == {part.pk: 3}

    def test_availability_excludes_the_edited_reservation(self, base):
        part = _make_part("Tente", stock=10)
        presta = _prestation(base, day_offset_start=0, hours=4, nom="A")
        resa = _reservation(base, presta, part, 4)

        debut, fin = self._period(base)

        assert compute_parts_availability([part.pk], debut, fin) == {part.pk: 6}
        assert compute_parts_availability(
            [part.pk], debut, fin, exclude_reservation_id=resa.pk
        ) == {part.pk: 10}

    def test_details_name_the_prestation_holding_the_stock(self, base):
        """Le détail nomme le responsable, réservation ou simple prévision."""

        part = _make_part("Table", stock=20)
        prevu = _prestation(
            base, day_offset_start=0, hours=4, part=part, qty=5, nom="Prévision"
        )
        reserve = _prestation(base, day_offset_start=0, hours=4, nom="Réservée")
        resa = _reservation(base, reserve, part, 3)

        debut, fin = self._period(base)
        details = compute_engagement_details([part.pk], debut, fin)

        par_nom = {entry["prestation_nom"]: entry for entry in details[part.pk]}
        assert par_nom["Prévision"] == {
            "prestation_id": prevu.pk,
            "prestation_nom": "Prévision",
            "quantite": 5,
            "origine": "prevision",
            "reservation_numeros": [],
        }
        assert par_nom["Réservée"] == {
            "prestation_id": reserve.pk,
            "prestation_nom": "Réservée",
            "quantite": 3,
            "origine": "reservations",
            "reservation_numeros": [resa.numero],
        }

    def test_shortage_is_raised_by_reservations_alone(self, base):
        part = _make_part("Tente", stock=5)
        presta = _prestation(base, day_offset_start=0, hours=4, nom="A")
        _reservation(base, presta, part, 4)

        debut, fin = self._period(base)
        result = compute_stock_availability(
            debut, fin, [{"part_id": part.pk, "quantite": 2}]
        )

        assert result["has_shortage"] is True
        line = result["lines"][0]
        assert line["reserved"] == 4
        assert line["available"] == 1
        assert line["missing"] == 1
