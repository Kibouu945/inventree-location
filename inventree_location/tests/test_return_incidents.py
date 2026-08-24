"""Tests du modèle de log d'incidents de retour (SCRUM-93)."""

from __future__ import annotations

from datetime import timedelta

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
    Reservation,
    ReturnIncident,
    ReturnIncidentType,
)
from inventree_location.views import (
    ReturnIncidentDetailView,
    ReturnIncidentListCreateView,
)

User = get_user_model()

INCIDENTS_URL = "/plugin/inventree-location/returns/incidents/"


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


class TestReturnIncidentModel:
    @pytest.mark.django_db
    def test_creation(self, ligne, magasinier):
        incident = ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.MISSING,
            qty=1,
            comment="Une tente manque",
            reported_by=magasinier,
        )
        assert incident.pk is not None
        assert incident.type == ReturnIncidentType.MISSING
        assert incident.qty == 1
        assert incident.reported_by_id == magasinier.pk
        assert incident.reported_at is not None

    @pytest.mark.django_db
    def test_str(self, ligne, magasinier):
        incident = ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.BROKEN,
            qty=2,
            reported_by=magasinier,
        )
        assert str(incident) == f"Incident #{incident.pk} (broken) — Ligne#{ligne.pk}"

    @pytest.mark.django_db
    def test_ordering_by_reported_at_desc(self, ligne, magasinier):
        first = ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.MISSING,
            qty=1,
            reported_by=magasinier,
        )
        second = ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.BROKEN,
            qty=1,
            reported_by=magasinier,
        )
        incidents = list(ReturnIncident.objects.all())
        assert incidents[0].pk == second.pk
        assert incidents[1].pk == first.pk

    @pytest.mark.django_db
    def test_cascade_delete_with_line(self, ligne, magasinier):
        incident = ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.MISSING,
            qty=1,
            reported_by=magasinier,
        )
        ligne.delete()
        assert ReturnIncident.objects.filter(pk=incident.pk).count() == 0


class TestReturnIncidentListCreate:
    @pytest.mark.django_db
    def test_create_incident_manquant(self, factory, magasinier, ligne):
        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.MISSING,
            "qty": 1,
            "comment": "Une tente manque au retour",
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED
        incident = ReturnIncident.objects.get()
        assert incident.type == ReturnIncidentType.MISSING
        assert incident.qty == 1
        assert incident.comment == "Une tente manque au retour"
        assert incident.reported_by_id == magasinier.pk

        # La ligne est mise à jour automatiquement, dans le vocabulaire
        # applicatif de `etat_retour` ("ok" / "manquant" / "casse").
        ligne.refresh_from_db()
        assert ligne.etat_retour == "manquant"
        assert ligne.commentaire == "Une tente manque au retour"

    @pytest.mark.django_db
    def test_create_incident_casse(self, factory, magasinier, ligne):
        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.BROKEN,
            "qty": 2,
            "comment": "Deux tentes déchirées",
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED
        incident = ReturnIncident.objects.get()
        assert incident.type == ReturnIncidentType.BROKEN

    @pytest.mark.django_db
    def test_quantite_depasse_livree_refusee(self, factory, magasinier, ligne):
        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.MISSING,
            "qty": 10,
            "comment": "",
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
            {"comment": "Retrouvé plus tard"},
            format="json",
        )
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentDetailView.as_view()(request, pk=incident.pk)

        assert response.status_code == status.HTTP_200_OK
        incident.refresh_from_db()
        assert incident.comment == "Retrouvé plus tard"

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


class TestReturnIncidentCoherenceLigne:
    """L'état de la ligne suit les incidents, y compris après édition."""

    @pytest.mark.django_db
    def test_casse_prime_sur_manquant(self, factory, magasinier, ligne):
        ReturnIncident.objects.create(
            line=ligne, type=ReturnIncidentType.MISSING, qty=1
        )

        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.BROKEN,
            "qty": 1,
            "comment": "",
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)

        assert (
            ReturnIncidentListCreateView.as_view()(request).status_code
            == status.HTTP_201_CREATED
        )

        ligne.refresh_from_db()
        assert ligne.etat_retour == "casse"

    @pytest.mark.django_db
    def test_commentaire_de_ligne_jamais_efface(self, factory, magasinier, ligne):
        ligne.commentaire = "Commentaire métier à conserver"
        ligne.save(update_fields=["commentaire"])

        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.MISSING,
            "qty": 1,
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)

        ReturnIncidentListCreateView.as_view()(request)

        ligne.refresh_from_db()
        assert ligne.commentaire == "Commentaire métier à conserver"

    @pytest.mark.django_db
    def test_cumul_des_incidents_plafonne(self, factory, magasinier, ligne):
        ReturnIncident.objects.create(
            line=ligne, type=ReturnIncidentType.MISSING, qty=3
        )

        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.BROKEN,
            "qty": 1,
            "comment": "",
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert ReturnIncident.objects.count() == 1

    @pytest.mark.django_db
    def test_quantite_nulle_refusee(self, factory, magasinier, ligne):
        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.MISSING,
            "qty": 0,
            "comment": "",
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert ReturnIncident.objects.count() == 0

    @pytest.mark.django_db
    def test_patch_du_type_realigne_la_ligne(self, factory, magasinier, ligne):
        incident = ReturnIncident.objects.create(
            line=ligne, type=ReturnIncidentType.MISSING, qty=1
        )
        ligne.refresh_from_db()

        request = factory.patch(
            f"{INCIDENTS_URL}{incident.pk}/",
            {"type": ReturnIncidentType.BROKEN},
            format="json",
        )
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentDetailView.as_view()(request, pk=incident.pk)

        assert response.status_code == status.HTTP_200_OK
        ligne.refresh_from_db()
        assert ligne.etat_retour == "casse"

    @pytest.mark.django_db
    def test_delete_du_dernier_incident_remet_la_ligne_a_zero(
        self, factory, magasinier, ligne
    ):
        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.MISSING,
            "qty": 1,
            "comment": "",
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)
        ReturnIncidentListCreateView.as_view()(request)

        ligne.refresh_from_db()
        assert ligne.etat_retour == "manquant"

        incident = ReturnIncident.objects.get()
        request = factory.delete(f"{INCIDENTS_URL}{incident.pk}/")
        force_authenticate(request, user=magasinier)

        ReturnIncidentDetailView.as_view()(request, pk=incident.pk)

        ligne.refresh_from_db()
        assert ligne.etat_retour == ""

    @pytest.mark.django_db
    def test_filtre_reservation_non_entier_refuse(self, factory, magasinier):
        request = factory.get(INCIDENTS_URL, {"reservation": "abc"})
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

class TestIncidentDetruit:
    """SCRUM-99 ajoute le type « détruit » : la ligne doit le refléter."""

    @pytest.mark.django_db
    def test_detruit_marque_la_ligne_cassee(self, factory, magasinier, ligne):
        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.DESTROYED,
            "qty": 1,
            "comment": "",
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED

        ligne.refresh_from_db()
        assert ligne.etat_retour == "casse"

    @pytest.mark.django_db
    def test_detruit_prime_sur_manquant(self, factory, magasinier, ligne):
        ReturnIncident.objects.create(
            line=ligne, type=ReturnIncidentType.MISSING, qty=1
        )

        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.DESTROYED,
            "qty": 1,
            "comment": "",
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)
        ReturnIncidentListCreateView.as_view()(request)

        ligne.refresh_from_db()
        assert ligne.etat_retour == "casse"
