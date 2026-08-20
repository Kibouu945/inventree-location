
from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location.models import (
    Groupe,
    LigneReservation,
    Manifestation,
    Prestation,
    Reservation,
    ReturnIncident,
    ReturnIncidentType,
)
from inventree_location.views import (
    ReturnIncidentDetailView,
    ReturnIncidentListCreateView,
    ReturnLossReportView,
)

from part.models import Part

User = get_user_model()

INCIDENTS_URL = "/plugin/inventree-location/returns/incidents/"
LOSS_REPORT_URL = "/plugin/inventree-location/returns/loss-report/"


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
def gestionnaire(db):
    from django.contrib.auth.models import Group

    from inventree_location import roles

    account = User.objects.create_user(username="gestion", password="pwd12345")
    account.groups.add(Group.objects.get(name=roles.GESTIONNAIRE))
    return account


@pytest.fixture
def reservation(db, magasinier):
    groupe = Groupe.objects.create(nom="Jambville", code="JAM")
    now = timezone.now()
    manifestation = Manifestation.objects.create(
        nom="Camp été 2026",
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
    )


class TestReturnIncidentListCreate:
    @pytest.mark.django_db
    def test_create_incident_manquant(self, factory, magasinier, ligne):
        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.MISSING,
            "qty": 1,
            "comment": "Une tente manque au retour",
            "bill_client": True,
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED
        incident = ReturnIncident.objects.get()
        assert incident.type == ReturnIncidentType.MISSING
        assert incident.qty == 1
        assert incident.comment == "Une tente manque au retour"
        assert incident.bill_client is True
        assert incident.reported_by_id == magasinier.pk

        # La ligne est mise à jour automatiquement.
        ligne.refresh_from_db()
        assert ligne.etat_retour == ReturnIncidentType.MISSING
        assert ligne.commentaire == "Une tente manque au retour"

    @pytest.mark.django_db
    def test_create_incident_casse(self, factory, magasinier, ligne):
        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.BROKEN,
            "qty": 2,
            "comment": "Deux tentes déchirées",
            "bill_client": False,
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED
        incident = ReturnIncident.objects.get()
        assert incident.type == ReturnIncidentType.BROKEN
        assert incident.bill_client is False

    @pytest.mark.django_db
    def test_quantite_depasse_livree_refusee(self, factory, magasinier, ligne):
        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.MISSING,
            "qty": 10,
            "comment": "",
            "bill_client": False,
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert ReturnIncident.objects.count() == 0

    @pytest.mark.django_db
    def test_type_invalide_refuse(self, factory, magasinier, ligne):
        payload = {
            "line": ligne.pk,
            "type": "perdu",
            "qty": 1,
            "comment": "",
            "bill_client": False,
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_list_filtre_par_reservation(self, factory, magasinier, ligne):
        ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.MISSING,
            qty=1,
            reported_by=magasinier,
        )

        request = factory.get(
            INCIDENTS_URL, {"reservation": ligne.reservation_id}
        )
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["line_part_name"] == "Tente 4 places"
        assert response.data[0]["line_reservation_numero"] == ligne.reservation.numero

    @pytest.mark.django_db
    def test_gestionnaire_refuse(self, factory, gestionnaire, ligne):
        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.MISSING,
            "qty": 1,
            "comment": "",
            "bill_client": False,
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=gestionnaire)

        response = ReturnIncidentListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestReturnIncidentDetail:
    @pytest.mark.django_db
    def test_patch_met_a_jour_commentaire(self, factory, magasinier, ligne):
        incident = ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.MISSING,
            qty=1,
            reported_by=magasinier,
        )

        request = factory.patch(
            f"{INCIDENTS_URL}{incident.pk}/",
            {"comment": "Retrouvé plus tard", "bill_client": False},
            format="json",
        )
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentDetailView.as_view()(request, pk=incident.pk)

        assert response.status_code == status.HTTP_200_OK
        incident.refresh_from_db()
        assert incident.comment == "Retrouvé plus tard"
        assert incident.bill_client is False

    @pytest.mark.django_db
    def test_delete_supprime_incident(self, factory, magasinier, ligne):
        incident = ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.MISSING,
            qty=1,
            reported_by=magasinier,
        )

        request = factory.delete(f"{INCIDENTS_URL}{incident.pk}/")
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentDetailView.as_view()(request, pk=incident.pk)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert ReturnIncident.objects.count() == 0


class TestReturnLossReport:
    @pytest.mark.django_db
    def test_rapport_agrege(self, factory, magasinier, ligne):
        ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.MISSING,
            qty=1,
            bill_client=True,
            reported_by=magasinier,
        )
        ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.MISSING,
            qty=1,
            bill_client=False,
            reported_by=magasinier,
        )
        ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.BROKEN,
            qty=1,
            reported_by=magasinier,
        )

        request = factory.get(LOSS_REPORT_URL)
        force_authenticate(request, user=magasinier)

        response = ReturnLossReportView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 3
        assert response.data["total_missing"] == 2
        assert response.data["total_broken"] == 1
        assert response.data["total_billed"] == 1
        assert response.data["by_part"][0]["part_name"] == "Tente 4 places"
        assert response.data["by_part"][0]["missing"] == 2
        assert response.data["by_part"][0]["broken"] == 1
        assert response.data["by_part"][0]["billed"] == 1
        assert response.data["by_reservation"][0]["reservation_numero"] == (
            ligne.reservation.numero
        )

    @pytest.mark.django_db
    def test_rapport_filtre_par_reservation(self, factory, magasinier, ligne):
        ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.MISSING,
            qty=1,
            reported_by=magasinier,
        )

        request = factory.get(
            LOSS_REPORT_URL, {"reservation": ligne.reservation_id}
        )
        force_authenticate(request, user=magasinier)

        response = ReturnLossReportView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["total_missing"] == 1