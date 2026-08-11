"""Tests du calcul de stock disponible au jour entier (STK-01)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from inventree_location.models import (
    Groupe,
    LignePrestation,
    Lieu,
    Manifestation,
    Prestation,
    RentableItem,
)
from inventree_location.stock import (
    compute_parts_availability,
    compute_prestation_stock,
    compute_stock_availability,
    day_ranges_overlap,
)

User = get_user_model()


@pytest.fixture
def base(db):
    now = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
    user = User.objects.create_user(username="bob", password="pwd12345")
    groupe = Groupe.objects.create(nom="Jambville", code="JAM")
    manifestation = Manifestation.objects.create(
        nom="Camp",
        date_debut=now,
        date_fin=now + timedelta(days=10),
        organisateur=user,
        groupe=groupe,
    )
    lieu = Lieu.objects.create(nom="Terrain")
    return {"now": now, "manifestation": manifestation, "lieu": lieu}


def _make_part(name, *, stock, virtual=False):
    from part.models import Part

    part = Part.objects.create(name=name)
    RentableItem.objects.create(part=part, stock_total=stock, is_virtual=virtual)
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
