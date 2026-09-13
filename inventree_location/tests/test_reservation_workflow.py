"""Tests du workflow de statut des réservations (SCRUM-74).

Deux couches :
- le service `workflow_service` (règles de transition, journal, validateur) ;
- l'endpoint `reservations/<pk>/transition/` (GET transitions dispo, PATCH).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location.models import (
    Prestation,
    Reservation,
    ReservationStatusLog,
    StatutReservation,
)
from inventree_location.services.workflow_service import (
    get_available_transitions,
    transition_reservation_status,
)
from inventree_location.views import ReservationTransitionView
from inventree_location.tests.factories import make_manifestation

User = get_user_model()

TRANSITION_URL = "/plugin/inventree-location/reservations/{pk}/transition/"


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def user(db):
    from django.contrib.auth.models import Group

    from inventree_location import roles

    account = User.objects.create_user(username="alice", password="pwd12345")
    account.groups.add(Group.objects.get(name=roles.GESTIONNAIRE))
    return account


@pytest.fixture
def prestation(db, user):
    now = timezone.now().replace(microsecond=0)
    manifestation = make_manifestation(
        nom="Camp été 2026",
        date_debut=now,
        date_fin=now + timedelta(days=7),
    )
    return Prestation.objects.create(
        manifestation=manifestation,
        nom="Installation",
        date_debut=now,
        date_fin=now + timedelta(hours=4),
    )


@pytest.fixture
def make_reservation(db, prestation, user):
    """Fabrique une réservation dans un statut donné."""

    def _make(statut=StatutReservation.BROUILLON):
        return Reservation.objects.create(
            prestation=prestation,
            demandeur=user,
            statut=statut,
            date_demande=timezone.now(),
        )

    return _make


class TestWorkflowService:
    def test_get_available_transitions_par_statut(self):
        assert get_available_transitions(StatutReservation.BROUILLON) == [
            StatutReservation.VALIDEE,
            StatutReservation.ANNULEE,
        ]
        assert get_available_transitions(StatutReservation.SOUMISE) == [
            StatutReservation.VALIDEE,
            StatutReservation.REFUSEE,
            StatutReservation.ANNULEE,
        ]

    def test_statut_terminal_aucune_transition(self):
        for terminal in (
            StatutReservation.CLOTUREE,
            StatutReservation.REFUSEE,
            StatutReservation.ANNULEE,
        ):
            assert get_available_transitions(terminal) == []

    @pytest.mark.django_db
    def test_transition_valide_change_statut_et_journalise(self, make_reservation):
        reservation = make_reservation(StatutReservation.SOUMISE)

        result = transition_reservation_status(
            reservation,
            StatutReservation.VALIDEE,
            comment="OK pour le camp",
        )

        reservation.refresh_from_db()
        assert reservation.statut == StatutReservation.VALIDEE
        assert result["old_status"] == StatutReservation.SOUMISE
        assert result["new_status"] == StatutReservation.VALIDEE

        log = reservation.status_logs.get()
        assert log.from_status == StatutReservation.SOUMISE
        assert log.to_status == StatutReservation.VALIDEE
        assert log.comment == "OK pour le camp"

    @pytest.mark.django_db
    def test_transition_vers_validee_renseigne_validateur(self, make_reservation, user):
        reservation = make_reservation(StatutReservation.SOUMISE)

        transition_reservation_status(reservation, StatutReservation.VALIDEE, user=user)

        reservation.refresh_from_db()
        assert reservation.validateur_id == user.pk
        assert reservation.status_logs.get().changed_by_id == user.pk

    @pytest.mark.django_db
    def test_transition_invalide_leve_erreur_sans_effet(self, make_reservation):
        reservation = make_reservation(StatutReservation.BROUILLON)

        with pytest.raises(ValidationError):
            # brouillon -> livree n'est pas autorisé.
            transition_reservation_status(reservation, StatutReservation.LIVREE)

        reservation.refresh_from_db()
        assert reservation.statut == StatutReservation.BROUILLON
        assert reservation.status_logs.count() == 0

    @pytest.mark.django_db
    def test_meme_statut_leve_erreur(self, make_reservation):
        reservation = make_reservation(StatutReservation.SOUMISE)

        with pytest.raises(ValidationError):
            transition_reservation_status(reservation, StatutReservation.SOUMISE)

        assert reservation.status_logs.count() == 0

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "depart",
        [
            StatutReservation.BROUILLON,
            StatutReservation.SOUMISE,
            StatutReservation.VALIDEE,
            StatutReservation.LIVREE,
            StatutReservation.RETOURNEE,
        ],
    )
    def test_annulation_possible_depuis_tout_etat_actif(self, make_reservation, depart):
        reservation = make_reservation(depart)

        transition_reservation_status(reservation, StatutReservation.ANNULEE)

        reservation.refresh_from_db()
        assert reservation.statut == StatutReservation.ANNULEE

    @pytest.mark.django_db
    def test_cycle_nominal_complet(self, make_reservation):
        reservation = make_reservation(StatutReservation.SOUMISE)

        for cible in (
            StatutReservation.VALIDEE,
            StatutReservation.LIVREE,
            StatutReservation.RETOURNEE,
            StatutReservation.CLOTUREE,
        ):
            transition_reservation_status(reservation, cible)

        reservation.refresh_from_db()
        assert reservation.statut == StatutReservation.CLOTUREE
        assert reservation.status_logs.count() == 4


class TestTransitionEndpoint:
    @pytest.mark.django_db
    def test_get_retourne_transitions_disponibles(
        self, factory, user, make_reservation
    ):
        reservation = make_reservation(StatutReservation.SOUMISE)
        request = factory.get(TRANSITION_URL.format(pk=reservation.pk))
        force_authenticate(request, user=user)

        response = ReservationTransitionView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["current_status"] == StatutReservation.SOUMISE
        assert StatutReservation.VALIDEE in response.data["available_transitions"]

    @pytest.mark.django_db
    def test_patch_applique_transition_et_journalise(
        self, factory, user, make_reservation
    ):
        reservation = make_reservation(StatutReservation.SOUMISE)
        request = factory.patch(
            TRANSITION_URL.format(pk=reservation.pk),
            {"statut": StatutReservation.VALIDEE, "comment": "go"},
            format="json",
        )
        force_authenticate(request, user=user)

        response = ReservationTransitionView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["new_status"] == StatutReservation.VALIDEE

        reservation.refresh_from_db()
        assert reservation.statut == StatutReservation.VALIDEE
        log = reservation.status_logs.get()
        assert log.to_status == StatutReservation.VALIDEE
        assert log.comment == "go"
        assert log.changed_by_id == user.pk

    @pytest.mark.django_db
    def test_patch_transition_invalide_renvoie_400(
        self, factory, user, make_reservation
    ):
        reservation = make_reservation(StatutReservation.BROUILLON)
        request = factory.patch(
            TRANSITION_URL.format(pk=reservation.pk),
            {"statut": StatutReservation.CLOTUREE},
            format="json",
        )
        force_authenticate(request, user=user)

        response = ReservationTransitionView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        reservation.refresh_from_db()
        assert reservation.statut == StatutReservation.BROUILLON

    @pytest.mark.django_db
    def test_patch_statut_inconnu_renvoie_400(self, factory, user, make_reservation):
        reservation = make_reservation(StatutReservation.SOUMISE)
        request = factory.patch(
            TRANSITION_URL.format(pk=reservation.pk),
            {"statut": "inexistant"},
            format="json",
        )
        force_authenticate(request, user=user)

        response = ReservationTransitionView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_patch_reservation_introuvable_renvoie_404(self, factory, user):
        request = factory.patch(
            TRANSITION_URL.format(pk=999999),
            {"statut": StatutReservation.VALIDEE},
            format="json",
        )
        force_authenticate(request, user=user)

        response = ReservationTransitionView.as_view()(request, pk=999999)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert ReservationStatusLog.objects.count() == 0


@pytest.mark.django_db
class TestArbitrageRbac:
    """Seuls gestionnaire / admin peuvent valider ou refuser (arbitrage)."""

    def _lecteur(self):
        from django.contrib.auth.models import Group

        from inventree_location import roles

        account = User.objects.create_user(username="lecteur", password="pwd12345")
        account.groups.add(Group.objects.get(name=roles.LECTEUR))
        return account

    @pytest.mark.parametrize("cible", ["validee", "refusee"])
    def test_un_role_sans_arbitrage_est_refuse(self, factory, make_reservation, cible):
        reservation = make_reservation(StatutReservation.SOUMISE)
        request = factory.patch(
            TRANSITION_URL.format(pk=reservation.pk),
            {"statut": cible},
            format="json",
        )
        force_authenticate(request, user=self._lecteur())

        response = ReservationTransitionView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        reservation.refresh_from_db()
        assert reservation.statut == StatutReservation.SOUMISE

    def test_gestionnaire_peut_valider(self, factory, user, make_reservation):
        reservation = make_reservation(StatutReservation.SOUMISE)
        request = factory.patch(
            TRANSITION_URL.format(pk=reservation.pk),
            {"statut": StatutReservation.VALIDEE},
            format="json",
        )
        force_authenticate(request, user=user)

        response = ReservationTransitionView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_200_OK
        reservation.refresh_from_db()
        assert reservation.statut == StatutReservation.VALIDEE
