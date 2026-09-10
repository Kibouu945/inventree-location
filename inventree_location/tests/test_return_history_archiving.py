from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location.archiving import ARCHIVE_AFTER_DAYS, archive_old_reservations
from inventree_location.models import (
    Prestation,
    Reservation,
    StatutReservation,
)
from inventree_location.views import ReservationListCreateView
from inventree_location.tests.factories import make_manifestation

User = get_user_model()

RESERVATION_LIST_URL = "/plugin/inventree-location/reservations/"


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def user(db):
    from django.contrib.auth.models import Group

    from inventree_location import roles

    account = User.objects.create_user(username="bob", password="pwd12345")
    account.groups.add(Group.objects.get(name=roles.GESTIONNAIRE))
    return account


@pytest.fixture
def prestation(db, user):
    now = timezone.now().replace(microsecond=0)
    manifestation = make_manifestation(
        nom="Camp indexation",
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
    def _make(statut=StatutReservation.CLOTUREE, date_demande=None, is_archived=False):
        reservation = Reservation.objects.create(
            prestation=prestation,
            demandeur=user,
            statut=statut,
            date_demande=date_demande or timezone.now(),
        )
        if is_archived:
            reservation.is_archived = True
            reservation.save(update_fields=["is_archived"])
        return reservation

    return _make


class TestArchiving:
    @pytest.mark.django_db
    def test_old_closed_reservation_gets_archived(self, make_reservation):
        old_date = timezone.now() - timedelta(days=800)
        reservation = make_reservation(
            statut=StatutReservation.CLOTUREE, date_demande=old_date
        )

        count = archive_old_reservations()

        reservation.refresh_from_db()
        assert count == 1
        assert reservation.is_archived is True

    @pytest.mark.django_db
    def test_recent_closed_reservation_is_not_archived(self, make_reservation):
        recent_date = timezone.now() - timedelta(days=30)
        reservation = make_reservation(
            statut=StatutReservation.CLOTUREE, date_demande=recent_date
        )

        count = archive_old_reservations()

        reservation.refresh_from_db()
        assert count == 0
        assert reservation.is_archived is False

    @pytest.mark.django_db
    def test_open_reservation_is_never_archived(self, make_reservation):
        old_date = timezone.now() - timedelta(days=900)
        reservation = make_reservation(
            statut=StatutReservation.VALIDEE, date_demande=old_date
        )

        count = archive_old_reservations()

        reservation.refresh_from_db()
        assert count == 0
        assert reservation.is_archived is False


class TestReservationListPaginationAndArchiving:
    @pytest.mark.django_db
    def test_list_excludes_archived_by_default(self, factory, user, make_reservation):
        make_reservation(statut=StatutReservation.CLOTUREE, is_archived=True)
        make_reservation(statut=StatutReservation.VALIDEE, is_archived=False)

        request = factory.get(RESERVATION_LIST_URL)
        force_authenticate(request, user=user)
        response = ReservationListCreateView.as_view()(request)

        assert response.status_code == 200
        assert response.data["count"] == 1

    @pytest.mark.django_db
    def test_list_can_include_archived(self, factory, user, make_reservation):
        make_reservation(statut=StatutReservation.CLOTUREE, is_archived=True)
        make_reservation(statut=StatutReservation.VALIDEE, is_archived=False)

        request = factory.get(RESERVATION_LIST_URL, {"include_archived": "1"})
        force_authenticate(request, user=user)
        response = ReservationListCreateView.as_view()(request)

        assert response.status_code == 200
        assert response.data["count"] == 2

    @pytest.mark.django_db
    def test_list_response_is_paginated(self, factory, user, make_reservation):
        for _ in range(3):
            make_reservation(statut=StatutReservation.VALIDEE)

        request = factory.get(RESERVATION_LIST_URL, {"limit": "2"})
        force_authenticate(request, user=user)
        response = ReservationListCreateView.as_view()(request)

        assert response.status_code == 200
        assert response.data["count"] == 3
        assert len(response.data["results"]) == 2


class TestArchivageTracabilite:
    @pytest.mark.django_db
    def test_archivage_horodate_la_reservation(self, make_reservation):
        """`queryset.update()` court-circuite `auto_now` : posé explicitement."""

        old_date = timezone.now() - timedelta(days=ARCHIVE_AFTER_DAYS + 1)
        reservation = make_reservation(
            statut=StatutReservation.CLOTUREE, date_demande=old_date
        )
        Reservation.objects.filter(pk=reservation.pk).update(updated_at=old_date)

        archive_old_reservations()

        reservation.refresh_from_db()
        assert reservation.is_archived is True
        assert reservation.updated_at > old_date
