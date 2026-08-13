"""Tests de la détection de conflits basée sur le stock (US-03 / SCRUM-76).

Couvre le moteur `detect_reservation_conflicts` (aucun conflit, conflit
partiel/total, article virtuel ignoré), l'endpoint de check (200 / 409) et
le refus de validation d'une réservation en conflit non forcé.
"""

from datetime import timedelta

import pytest
from rest_framework import serializers, status
from rest_framework.test import APIRequestFactory, force_authenticate

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from inventree_location import roles
from inventree_location.conflicts import (
    detect_reservation_conflicts,
    reservation_has_conflicts,
)
from inventree_location.models import (
    Groupe,
    LignePrestation,
    LigneReservation,
    Manifestation,
    Prestation,
    RentableItem,
    Reservation,
    StatutReservation,
)
from inventree_location.serializers import ReservationSerializer
from inventree_location.services.workflow_service import (
    transition_reservation_status,
)
from inventree_location.views import ReservationConflictCheckView

from part.models import Part

User = get_user_model()


@pytest.fixture
def gestionnaire(db):
    group, _created = Group.objects.get_or_create(name=roles.GESTIONNAIRE)
    account = User.objects.create_user(username="alice", password="pwd12345")
    account.groups.add(group)
    return account


@pytest.fixture
def stock_setup(db):
    """Un part avec stock_total=1 et une réservation validée qui le réserve."""

    user = User.objects.create_user(username="bob", password="pwd12345")
    groupe = Groupe.objects.create(nom="Jambville", code="JAM")
    now = timezone.now().replace(microsecond=0)
    manifestation = Manifestation.objects.create(
        nom="Camp",
        date_debut=now,
        date_fin=now + timedelta(days=5),
        organisateur=user,
        groupe=groupe,
    )
    prestation = Prestation.objects.create(
        manifestation=manifestation,
        nom="P",
        date_debut=now,
        date_fin=now + timedelta(days=5),
    )
    part = Part.objects.create(name="Tente")
    RentableItem.objects.create(part=part, is_rentable=True, stock_total=1)

    existing = Reservation.objects.create(
        prestation=prestation,
        demandeur=user,
        date_demande=now,
        statut=StatutReservation.VALIDEE,
        date_retrait_prevue=now,
        date_retour_prevue=now + timedelta(days=2),
    )
    LigneReservation.objects.create(
        reservation=existing, part=part, quantite_demandee=1
    )

    return {
        "user": user,
        "prestation": prestation,
        "part": part,
        "existing": existing,
        "now": now,
    }


def _make_candidate(
    stock_setup, *, qty, statut=StatutReservation.SOUMISE, forced=False
):
    now = stock_setup["now"]
    candidate = Reservation.objects.create(
        prestation=stock_setup["prestation"],
        demandeur=stock_setup["user"],
        date_demande=now,
        statut=statut,
        forced=forced,
        date_retrait_prevue=now + timedelta(days=1),
        date_retour_prevue=now + timedelta(days=3),
    )
    LigneReservation.objects.create(
        reservation=candidate, part=stock_setup["part"], quantite_demandee=qty
    )
    return candidate


@pytest.mark.django_db
def test_no_conflict_when_enough_stock(stock_setup):
    """Stock 1 déjà réservé 1 : une demande sur une période disjointe passe."""

    now = stock_setup["now"]
    candidate = Reservation.objects.create(
        prestation=stock_setup["prestation"],
        demandeur=stock_setup["user"],
        date_demande=now,
        statut=StatutReservation.SOUMISE,
        date_retrait_prevue=now + timedelta(days=10),
        date_retour_prevue=now + timedelta(days=12),
    )
    LigneReservation.objects.create(
        reservation=candidate, part=stock_setup["part"], quantite_demandee=1
    )

    result = detect_reservation_conflicts(candidate)

    assert result["has_conflict"] is False
    assert result["conflicts"] == []


@pytest.mark.django_db
def test_total_conflict_when_stock_exhausted(stock_setup):
    """Stock 1 déjà réservé 1 sur période chevauchante : demande 1 → conflit."""

    candidate = _make_candidate(stock_setup, qty=1)

    result = detect_reservation_conflicts(candidate)

    assert result["has_conflict"] is True
    assert len(result["conflicts"]) == 1
    conflict = result["conflicts"][0]
    assert conflict["part_id"] == stock_setup["part"].pk
    assert conflict["total_stock"] == 1
    assert conflict["already_reserved_quantity"] == 1
    assert conflict["available_quantity"] == 0
    assert conflict["missing_quantity"] == 1
    ids = [c["reservation_id"] for c in conflict["conflicting_reservations"]]
    assert stock_setup["existing"].pk in ids
    assert conflict["suggestions"]


@pytest.mark.django_db
def test_partial_conflict_when_requesting_more_than_available(stock_setup):
    """Stock 3, déjà réservé 1 : une demande de 3 dépasse le dispo (2)."""

    RentableItem.objects.filter(part=stock_setup["part"]).update(stock_total=3)

    candidate = _make_candidate(stock_setup, qty=3)

    result = detect_reservation_conflicts(candidate)

    assert result["has_conflict"] is True
    conflict = result["conflicts"][0]
    assert conflict["total_stock"] == 3
    assert conflict["available_quantity"] == 2
    assert conflict["missing_quantity"] == 1


@pytest.mark.django_db
def test_other_prestation_forecast_is_counted(stock_setup):
    """Le prévisionnel d'une autre prestation engage le stock, sans réservation.

    Sans cela, la détection de conflit et le catalogue annonçaient deux
    disponibilités différentes pour le même article à la même date.
    """

    now = stock_setup["now"]
    part = stock_setup["part"]
    RentableItem.objects.filter(part=part).update(stock_total=5)

    autre = Prestation.objects.create(
        manifestation=stock_setup["prestation"].manifestation,
        nom="Autre",
        date_debut=now,
        date_fin=now + timedelta(days=5),
    )
    LignePrestation.objects.create(prestation=autre, part=part, quantite=3)

    candidate = _make_candidate(stock_setup, qty=2)

    result = detect_reservation_conflicts(candidate)

    # 1 réservé par la résa existante + 3 prévus par l'autre prestation.
    assert result["has_conflict"] is True
    conflict = result["conflicts"][0]
    assert conflict["already_reserved_quantity"] == 4
    assert conflict["available_quantity"] == 1

    # La prestation qui retient le stock sans réservation est nommée.
    par_nom = {
        entry["prestation_nom"]: entry
        for entry in conflict["conflicting_prestations"]
    }
    assert par_nom["Autre"]["quantite"] == 3
    assert par_nom["Autre"]["origine"] == "prevision"
    assert par_nom["Autre"]["reservation_numeros"] == []
    assert par_nom["P"]["origine"] == "reservations"
    assert par_nom["P"]["reservation_numeros"] == [stock_setup["existing"].numero]


@pytest.mark.django_db
def test_own_prestation_forecast_does_not_block_its_reservation(stock_setup):
    """Une réservation ne se heurte pas au prévisionnel qu'elle matérialise."""

    part = stock_setup["part"]
    RentableItem.objects.filter(part=part).update(stock_total=5)
    LignePrestation.objects.create(
        prestation=stock_setup["prestation"], part=part, quantite=4
    )

    candidate = _make_candidate(stock_setup, qty=4)

    result = detect_reservation_conflicts(candidate)

    # Seule la réservation existante (1) est opposable, pas les 4 prévus.
    assert result["has_conflict"] is False


@pytest.mark.django_db
def test_virtual_item_is_ignored(stock_setup):
    """Un article virtuel (service) n'entraîne jamais de conflit de stock."""

    now = stock_setup["now"]
    virtual_part = Part.objects.create(name="Nettoyage")
    RentableItem.objects.create(
        part=virtual_part, is_rentable=True, is_virtual=True, stock_total=0
    )
    candidate = Reservation.objects.create(
        prestation=stock_setup["prestation"],
        demandeur=stock_setup["user"],
        date_demande=now,
        statut=StatutReservation.SOUMISE,
        date_retrait_prevue=now + timedelta(days=1),
        date_retour_prevue=now + timedelta(days=3),
    )
    LigneReservation.objects.create(
        reservation=candidate, part=virtual_part, quantite_demandee=5
    )

    assert reservation_has_conflicts(candidate) is False


@pytest.mark.django_db
def test_endpoint_returns_409_on_conflict(gestionnaire, stock_setup):
    candidate = _make_candidate(stock_setup, qty=1)
    factory = APIRequestFactory()
    request = factory.get(
        f"/plugin/inventree-location/reservations/{candidate.pk}/conflicts/"
    )
    force_authenticate(request, user=gestionnaire)

    response = ReservationConflictCheckView.as_view()(request, pk=candidate.pk)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["has_conflict"] is True


@pytest.mark.django_db
def test_endpoint_returns_200_without_conflict(gestionnaire, stock_setup):
    now = stock_setup["now"]
    candidate = Reservation.objects.create(
        prestation=stock_setup["prestation"],
        demandeur=stock_setup["user"],
        date_demande=now,
        statut=StatutReservation.SOUMISE,
        date_retrait_prevue=now + timedelta(days=20),
        date_retour_prevue=now + timedelta(days=22),
    )
    LigneReservation.objects.create(
        reservation=candidate, part=stock_setup["part"], quantite_demandee=1
    )
    factory = APIRequestFactory()
    request = factory.get(
        f"/plugin/inventree-location/reservations/{candidate.pk}/conflicts/"
    )
    force_authenticate(request, user=gestionnaire)

    response = ReservationConflictCheckView.as_view()(request, pk=candidate.pk)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["has_conflict"] is False


@pytest.mark.django_db
def test_validation_refused_when_validee_and_conflict(stock_setup):
    """Passer en `validée` avec conflit non forcé lève une ValidationError."""

    candidate = _make_candidate(stock_setup, qty=1, statut=StatutReservation.VALIDEE)

    with pytest.raises(serializers.ValidationError):
        ReservationSerializer()._validate_stock_conflicts_if_needed(candidate)


@pytest.mark.django_db
def test_forced_reservation_bypasses_validation(stock_setup):
    """`forced=True` permet de valider malgré le conflit (US-03)."""

    candidate = _make_candidate(
        stock_setup, qty=1, statut=StatutReservation.VALIDEE, forced=True
    )

    # Ne doit pas lever.
    ReservationSerializer()._validate_stock_conflicts_if_needed(candidate)


@pytest.mark.django_db
def test_non_validee_status_is_not_blocked(stock_setup):
    """Un statut autre que `validée` n'est jamais bloqué par le check conflit."""

    candidate = _make_candidate(stock_setup, qty=1, statut=StatutReservation.SOUMISE)

    # Ne doit pas lever malgré le conflit sous-jacent.
    ReservationSerializer()._validate_stock_conflicts_if_needed(candidate)


@pytest.mark.django_db
def test_transition_to_validee_blocked_on_conflict(stock_setup):
    """Le garde-fou stock s'applique aussi via l'endpoint de transition."""

    candidate = _make_candidate(stock_setup, qty=1, statut=StatutReservation.SOUMISE)

    with pytest.raises(serializers.ValidationError):
        transition_reservation_status(candidate, StatutReservation.VALIDEE)

    candidate.refresh_from_db()
    assert candidate.statut == StatutReservation.SOUMISE
    assert candidate.status_logs.count() == 0


@pytest.mark.django_db
def test_transition_to_validee_allowed_when_forced(stock_setup):
    """`forced=True` valide malgré le conflit, même par la transition (US-03)."""

    candidate = _make_candidate(
        stock_setup, qty=1, statut=StatutReservation.SOUMISE, forced=True
    )

    transition_reservation_status(candidate, StatutReservation.VALIDEE)

    candidate.refresh_from_db()
    assert candidate.statut == StatutReservation.VALIDEE
