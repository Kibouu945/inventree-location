"""Tests de la détection de conflits basée sur le stock (US-03 / SCRUM-76)."""

from datetime import timedelta

import pytest
from rest_framework import serializers, status
from rest_framework.test import APIRequestFactory, force_authenticate

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from inventree_location import roles
from inventree_location.conflicts import (
    detect_reservation_conflicts,
    list_current_conflicts,
    reservation_has_conflicts,
)
from inventree_location.tests.factories import (
    fixer_stock,
    make_manifestation,
    mettre_en_stock,
)
from inventree_location.models import (
    Lieu,
    LignePrestation,
    LigneReservation,
    Prestation,
    RentableItem,
    Reservation,
    StatutReservation,
)
from inventree_location.serializers import ReservationSerializer
from inventree_location.services.workflow_service import (
    transition_reservation_status,
)
from inventree_location.views import (
    ConflictHistoryResolveView,
    ReservationConflictCheckView,
)
from inventree_location.views import StockAvailabilityCheckView

from part.models import Part, PartCategory

User = get_user_model()


@pytest.fixture
def gestionnaire(db):
    group, _created = Group.objects.get_or_create(name=roles.GESTIONNAIRE)
    account = User.objects.create_user(username="alice", password="pwd12345")
    account.groups.add(group)
    return account


@pytest.fixture
def stock_setup(db):
    """Un part avec 1 exemplaire en stock et une réservation validée."""

    user = User.objects.create_user(username="bob", password="pwd12345")
    now = timezone.now().replace(microsecond=0)
    manifestation = make_manifestation(
        nom="Camp",
        date_debut=now,
        date_fin=now + timedelta(days=5),
    )
    prestation = Prestation.objects.create(
        manifestation=manifestation,
        nom="P",
        date_debut=now,
        date_fin=now + timedelta(days=5),
    )
    part = Part.objects.create(name="Tente")
    RentableItem.objects.create(part=part, is_rentable=True)
    mettre_en_stock(part, 1)

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

    fixer_stock(stock_setup["part"], 3)

    candidate = _make_candidate(stock_setup, qty=3)

    result = detect_reservation_conflicts(candidate)

    assert result["has_conflict"] is True
    conflict = result["conflicts"][0]
    assert conflict["total_stock"] == 3
    assert conflict["available_quantity"] == 2
    assert conflict["missing_quantity"] == 1


@pytest.mark.django_db
def test_other_prestation_forecast_is_counted(stock_setup):
    """Le prévisionnel d'une autre prestation engage le stock, sans réservation."""

    now = stock_setup["now"]
    part = stock_setup["part"]
    fixer_stock(part, 5)

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
    fixer_stock(part, 5)
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
        part=virtual_part, is_rentable=True, is_virtual=True
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
def test_forced_reservation_bypasses_the_block(stock_setup):
    """`forced=True` valide malgré le conflit (US-03, « forcer malgré »)."""

    candidate = _make_candidate(
        stock_setup, qty=1, statut=StatutReservation.VALIDEE, forced=True
    )

    ReservationSerializer()._validate_stock_conflicts_if_needed(candidate)


@pytest.mark.django_db
def test_non_validee_status_is_saved_despite_conflict(stock_setup):
    """Une réservation non validée se sauvegarde malgré le conflit."""

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


@pytest.mark.django_db
def test_day_granularity_detects_same_day_conflict(stock_setup):
    """Conflit même jour même si les heures ne se chevauchent pas strictement."""

    now = stock_setup["now"]
    candidate = Reservation.objects.create(
        prestation=stock_setup["prestation"],
        demandeur=stock_setup["user"],
        date_demande=now,
        statut=StatutReservation.SOUMISE,
        date_retrait_prevue=now.replace(hour=23, minute=0),
        date_retour_prevue=now.replace(hour=23, minute=30),
    )
    LigneReservation.objects.create(
        reservation=candidate, part=stock_setup["part"], quantite_demandee=1
    )

    result = detect_reservation_conflicts(candidate)
    assert result["has_conflict"] is True


@pytest.mark.django_db
def test_stock_availability_endpoint_returns_409_on_shortage(gestionnaire, stock_setup):
    now = stock_setup["now"]
    factory = APIRequestFactory()
    request = factory.get(
        "/plugin/inventree-location/reservations/check-stock/",
        {
            "part": stock_setup["part"].pk,
            "quantity": 1,
            "date_retrait_prevue": (now + timedelta(hours=1)).isoformat(),
            "date_retour_prevue": (now + timedelta(hours=2)).isoformat(),
        },
    )
    force_authenticate(request, user=gestionnaire)

    response = StockAvailabilityCheckView.as_view()(request)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["has_conflict"] is True


@pytest.mark.django_db
def test_stock_availability_endpoint_returns_200_when_available(gestionnaire, stock_setup):
    now = stock_setup["now"]
    factory = APIRequestFactory()
    request = factory.get(
        "/plugin/inventree-location/reservations/check-stock/",
        {
            "part": stock_setup["part"].pk,
            "quantity": 1,
            "date_retrait_prevue": (now + timedelta(days=7)).isoformat(),
            "date_retour_prevue": (now + timedelta(days=8)).isoformat(),
        },
    )
    force_authenticate(request, user=gestionnaire)

    response = StockAvailabilityCheckView.as_view()(request)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["has_conflict"] is False


@pytest.mark.django_db
def test_resoudre_un_conflit_de_stock_exige_que_la_penurie_ait_disparu(
    gestionnaire, stock_setup
):
    """« Résoudre » ne doit jamais taire une pénurie encore réelle."""

    from inventree_location.models import ConflictHistory, ConflictState, ConflictType

    candidate = _make_candidate(stock_setup, qty=1)
    entree = ConflictHistory.objects.create(
        conflict_type=ConflictType.STOCK,
        state=ConflictState.OPEN,
        reservation=candidate,
        part=stock_setup["part"],
        period_start=candidate.date_retrait_prevue,
        period_end=candidate.date_retour_prevue,
    )

    factory = APIRequestFactory()

    def resoudre():
        request = factory.patch(
            f"/plugin/inventree-location/conflicts/history/{entree.pk}/resolve/",
            {"note": "handled"},
            format="json",
        )
        force_authenticate(request, user=gestionnaire)
        return ConflictHistoryResolveView.as_view()(request, pk=entree.pk)

    refus = resoudre()

    assert refus.status_code == status.HTTP_409_CONFLICT
    assert "il manque" in refus.data["reason"]
    assert "Tente" in refus.data["reason"]

    entree.refresh_from_db()
    assert entree.state == ConflictState.OPEN

    # Cause levée : on réapprovisionne, la pénurie disparaît.
    fixer_stock(stock_setup["part"], 10)

    accepte = resoudre()

    assert accepte.status_code == status.HTTP_200_OK
    entree.refresh_from_db()
    assert entree.state == ConflictState.RESOLVED


@pytest.mark.django_db
def test_une_penurie_nee_apres_coup_entre_au_registre(gestionnaire, stock_setup):
    """Le stock peut baisser hors de toute écriture de réservation."""

    from inventree_location.conflicts import sync_conflict_registry
    from inventree_location.models import ConflictHistory, ConflictState, ConflictType

    # La réservation validée du fixture tient sur le stock existant.
    assert ConflictHistory.objects.count() == 0

    # Le stock disparaît après coup.
    fixer_stock(stock_setup["part"], 0)

    ouvertes = sync_conflict_registry()

    assert ouvertes >= 1
    entree = ConflictHistory.objects.filter(
        conflict_type=ConflictType.STOCK,
        state=ConflictState.OPEN,
        reservation=stock_setup["existing"],
    ).first()
    assert entree is not None
    assert entree.part_id == stock_setup["part"].pk
    assert entree.details["missing_quantity"] >= 1

    # Idempotent : une seconde passe n'ouvre pas de doublon.
    assert sync_conflict_registry() == 0
    assert ConflictHistory.objects.filter(state=ConflictState.OPEN).count() == 1


@pytest.mark.django_db
def test_la_synchronisation_ne_referme_rien(gestionnaire, stock_setup):
    """Clore reste un geste humain, vérifié par `conflict_still_active`."""

    from inventree_location.conflicts import sync_conflict_registry
    from inventree_location.models import ConflictHistory, ConflictState

    fixer_stock(stock_setup["part"], 0)
    sync_conflict_registry()

    fixer_stock(stock_setup["part"], 50)
    sync_conflict_registry()

    assert ConflictHistory.objects.filter(state=ConflictState.OPEN).count() == 1


class TestCoutDuWidgetDeConflits:
    """Le coût de `list_current_conflicts` ne doit pas suivre le volume."""

    @staticmethod
    def _semer(nb_reservations, nb_articles=6):
        """Des réservations qui se chevauchent, sur un stock qui suffit."""

        categorie = PartCategory.objects.create(
            name=f"Charge {PartCategory.objects.count()}"
        )
        parts = []

        for rang in range(nb_articles):
            part = Part.objects.create(name=f"Article {rang}", category=categorie)
            RentableItem.objects.create(part=part, is_rentable=True)
            mettre_en_stock(part, 10_000)
            parts.append(part)

        demandeur = User.objects.create_user(
            username=f"semeur-{User.objects.count()}", password="pwd"
        )
        depart = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
        lieu = Lieu.objects.create(nom=f"Lieu {Lieu.objects.count()}", adresse="1 rue")
        manifestation = make_manifestation(
            nom=f"Saison {Prestation.objects.count()}",
            date_debut=depart,
            date_fin=depart + timedelta(days=60),
        )

        for rang in range(nb_reservations):
            debut = depart + timedelta(days=rang % 10)
            prestation = Prestation.objects.create(
                manifestation=manifestation,
                lieu=lieu,
                nom=f"Presta {Prestation.objects.count()}",
                date_debut=debut,
                date_fin=debut + timedelta(days=2),
            )
            reservation = Reservation.objects.create(
                prestation=prestation,
                demandeur=demandeur,
                statut=StatutReservation.VALIDEE,
                date_retrait_prevue=debut,
                date_retour_prevue=debut + timedelta(days=2),
            )

            for decalage in range(2):
                reservation.lignes.create(
                    part=parts[(rang + decalage) % nb_articles],
                    quantite_demandee=1,
                )

    @staticmethod
    def _mesurer():
        with CaptureQueriesContext(connection) as requetes:
            assert list_current_conflicts() == []

        return len(requetes)

    @pytest.mark.django_db
    def test_le_cout_ne_depend_pas_du_nombre_de_reservations(self):
        """Deux mesures plutôt qu'un plafond : vingt réservations, puis quatre-vingts."""

        self._semer(20)
        self._mesurer()  # la première passe amorce les caches
        vingt = self._mesurer()

        self._semer(60)

        assert self._mesurer() == vingt
