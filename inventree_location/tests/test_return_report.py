"""Tests for the return report feature."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from part.models import Part

from inventree_location.models import (
    Groupe,
    LigneReservation,
    Manifestation,
    Prestation,
    RentableItem,
    Reservation,
    ReturnIncident,
    ReturnIncidentType,
)
from inventree_location.services.return_report import build_return_report
from inventree_location.views import ReturnReportPdfView, ReturnReportView

User = get_user_model()

REPORT_URL = "/plugin/inventree-location/returns/reports/"


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def magasinier(db):
    from django.contrib.auth.models import Group

    from inventree_location import roles

    account = User.objects.create_user(username="mag", password="pwd12345")
    account.groups.add(Group.objects.get(name=roles.MAGASINIER))
    return account


@pytest.fixture
def reservation(db, magasinier):
    groupe = Groupe.objects.create(nom="Jambville", code="JAM")
    now = timezone.now()
    manifestation = Manifestation.objects.create(
        nom="Camp ete 2026",
        date_debut=now,
        date_fin=now + timedelta(days=7),
        organisateur=magasinier,
        groupe=groupe,
    )
    prestation = Prestation.objects.create(
        manifestation=manifestation,
        nom="Installation",
        date_debut=now,
        date_fin=now + timedelta(hours=4),
    )
    return Reservation.objects.create(
        prestation=prestation,
        demandeur=magasinier,
        date_demande=now,
        statut="livree",
    )


@pytest.fixture
def ligne(db, reservation):
    part = Part.objects.create(name="Tente 4 places")
    return LigneReservation.objects.create(
        reservation=reservation,
        part=part,
        quantite_demandee=3,
        quantite_livree=3,
        quantite_retournee=3,
    )


class TestBuildReturnReport:
    @pytest.mark.django_db
    def test_empty_report(self, reservation):
        report = build_return_report(reservation.pk)
        assert report["reservation_numero"] == reservation.numero
        assert report["totals"]["returned"] == 0
        assert report["total_extra"] == Decimal("0.00")

    @pytest.mark.django_db
    def test_report_with_incidents(self, ligne, magasinier):
        ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.MISSING,
            qty=1,
            reported_by=magasinier,
        )
        ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.BROKEN,
            qty=1,
            reported_by=magasinier,
        )
        ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.DESTROYED,
            qty=1,
            reported_by=magasinier,
        )

        report = build_return_report(ligne.reservation_id)
        assert report["totals"]["missing"] == 1
        assert report["totals"]["broken"] == 1
        assert report["totals"]["destroyed"] == 1
        assert report["totals"]["returned"] == 3

    @pytest.mark.django_db
    def test_report_extra_cost(self, ligne, magasinier):
        RentableItem.objects.create(
            part=ligne.part,
            valeur_remplacement=Decimal("50.00"),
            caution=Decimal("100.00"),
        )
        ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.MISSING,
            qty=2,
            reported_by=magasinier,
        )
        ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.DESTROYED,
            qty=1,
            reported_by=magasinier,
        )

        report = build_return_report(ligne.reservation_id)
        assert report["total_extra"] == Decimal("200.00")

    @pytest.mark.django_db
    def test_report_not_found(self):
        with pytest.raises(ValueError):
            build_return_report(99999)


class TestReturnReportView:
    @pytest.mark.django_db
    def test_get_report(self, factory, magasinier, ligne):
        request = factory.get(f"{REPORT_URL}{ligne.reservation_id}/")
        force_authenticate(request, user=magasinier)

        response = ReturnReportView.as_view()(request, pk=ligne.reservation_id)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["reservation_id"] == ligne.reservation_id

    @pytest.mark.django_db
    def test_get_report_not_found(self, factory, magasinier):
        request = factory.get(f"{REPORT_URL}99999/")
        force_authenticate(request, user=magasinier)

        response = ReturnReportView.as_view()(request, pk=99999)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestReturnReportPdfView:
    @pytest.mark.django_db
    def test_get_pdf(self, factory, magasinier, ligne):
        request = factory.get(f"{REPORT_URL}{ligne.reservation_id}/pdf/")
        force_authenticate(request, user=magasinier)

        response = ReturnReportPdfView.as_view()(request, pk=ligne.reservation_id)

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"