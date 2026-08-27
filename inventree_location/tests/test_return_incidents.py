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
    ReturnIncidentHistoryView,
    ReturnIncidentListCreateView,
    ReturnLossReportView,
)

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

    @pytest.mark.django_db
    def test_history_filters_recent_items_and_links_reservation(
        self, factory, magasinier, ligne
    ):
        older = ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.MISSING,
            qty=1,
            reported_by=magasinier,
            reported_at=timezone.now() - timedelta(days=120),
        )
        recent = ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.BROKEN,
            qty=1,
            reported_by=magasinier,
            reported_at=timezone.now() - timedelta(days=10),
        )

        request = factory.get(
            "/plugin/inventree-location/returns/history/",
            {"type": ReturnIncidentType.BROKEN, "object": "Tente", "event": "Camp"},
        )
        force_authenticate(request, user=magasinier)

        response = ReturnIncidentHistoryView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["id"] == recent.id
        assert response.data[0]["reservation_id"] == ligne.reservation_id
        assert response.data[0]["reservation_number"] == ligne.reservation.numero
        assert response.data[0]["part_name"] == "Tente 4 places"
        assert response.data[0]["event_name"] == "Camp été 2026"
        assert older.id not in [item["id"] for item in response.data]


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


class TestHistoriqueFiltres:
    """Chaque filtre isolément : appliqués ensemble, ils se masquaient."""

    HISTORY_URL = "/plugin/inventree-location/returns/history/"

    def _incident(self, ligne, magasinier, jours, type_incident):
        return ReturnIncident.objects.create(
            line=ligne,
            type=type_incident,
            qty=1,
            reported_by=magasinier,
            reported_at=timezone.now() - timedelta(days=jours),
        )

    def _get(self, factory, magasinier, params=None):
        request = factory.get(self.HISTORY_URL, params or {})
        force_authenticate(request, user=magasinier)
        return ReturnIncidentHistoryView.as_view()(request)

    @pytest.mark.django_db
    def test_borne_des_90_jours(self, factory, magasinier, ligne):
        dedans = self._incident(ligne, magasinier, 89, ReturnIncidentType.MISSING)
        dehors = self._incident(ligne, magasinier, 91, ReturnIncidentType.MISSING)

        response = self._get(factory, magasinier)

        ids = [item["id"] for item in response.data]
        assert dedans.id in ids
        assert dehors.id not in ids

    @pytest.mark.django_db
    def test_filtre_type_seul(self, factory, magasinier, ligne):
        casse = self._incident(ligne, magasinier, 1, ReturnIncidentType.BROKEN)
        self._incident(ligne, magasinier, 1, ReturnIncidentType.MISSING)

        response = self._get(
            factory, magasinier, {"type": ReturnIncidentType.BROKEN}
        )

        assert [item["id"] for item in response.data] == [casse.id]

    @pytest.mark.django_db
    def test_filtre_objet_seul(self, factory, magasinier, ligne):
        attendu = self._incident(ligne, magasinier, 1, ReturnIncidentType.MISSING)

        assert [item["id"] for item in self._get(
            factory, magasinier, {"object": "tente"}
        ).data] == [attendu.id]
        assert self._get(factory, magasinier, {"object": "zzz"}).data == []

    @pytest.mark.django_db
    def test_filtre_evenement_seul(self, factory, magasinier, ligne):
        attendu = self._incident(ligne, magasinier, 1, ReturnIncidentType.MISSING)

        assert [item["id"] for item in self._get(
            factory, magasinier, {"event": "camp"}
        ).data] == [attendu.id]
        assert self._get(factory, magasinier, {"event": "zzz"}).data == []

    @pytest.mark.django_db
    def test_type_inconnu_refuse(self, factory, magasinier, ligne):
        """Une faute de frappe se lisait « aucun incident » en 200."""

        self._incident(ligne, magasinier, 1, ReturnIncidentType.MISSING)

        response = self._get(factory, magasinier, {"type": "nawak"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_historique_lisible_par_tous_les_roles(
        self, factory, gestionnaire, ligne
    ):
        """La lecture reste ouverte : `RoleBasedPermission` ne restreint que
        l'écriture. Le gestionnaire consulte donc l'historique sans le nourrir.
        """

        request = factory.get(self.HISTORY_URL)
        force_authenticate(request, user=gestionnaire)

        response = ReturnIncidentHistoryView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK


class TestCoexistenceCheckinEtIncidents:
    """Deux fonctionnalités écrivent `etat_retour` : elles doivent s'accorder.

    Le check-in retour (SCRUM-94) pose l'état depuis ses quantités, le journal
    d'incidents (SCRUM-93) le recalcule depuis les incidents. Supprimer le
    dernier incident effaçait l'état posé par le check-in.
    """

    @pytest.mark.django_db
    def test_suppression_dincident_preserve_letat_du_checkin(
        self, factory, magasinier, ligne
    ):
        ligne.quantite_retour_ok = ligne.quantite_demandee
        ligne.save(update_fields=["quantite_retour_ok"])

        incident = ReturnIncident.objects.create(
            line=ligne, type=ReturnIncidentType.MISSING, qty=1
        )

        request = factory.delete(f"{INCIDENTS_URL}{incident.pk}/")
        force_authenticate(request, user=magasinier)
        ReturnIncidentDetailView.as_view()(request, pk=incident.pk)

        ligne.refresh_from_db()
        assert ligne.etat_retour == "ok"

    @pytest.mark.django_db
    def test_sans_checkin_ni_incident_letat_reste_vide(
        self, factory, magasinier, ligne
    ):
        incident = ReturnIncident.objects.create(
            line=ligne, type=ReturnIncidentType.MISSING, qty=1
        )

        request = factory.delete(f"{INCIDENTS_URL}{incident.pk}/")
        force_authenticate(request, user=magasinier)
        ReturnIncidentDetailView.as_view()(request, pk=incident.pk)

        ligne.refresh_from_db()
        assert ligne.etat_retour == ""

    @pytest.mark.django_db
    def test_un_incident_prime_sur_le_checkin(self, factory, magasinier, ligne):
        ligne.quantite_retour_ok = ligne.quantite_demandee
        ligne.save(update_fields=["quantite_retour_ok"])

        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.BROKEN,
            "qty": 1,
            "comment": "",
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)
        ReturnIncidentListCreateView.as_view()(request)

        ligne.refresh_from_db()
        assert ligne.etat_retour == "casse"


class TestReturnLossReport:
    """Rapport de pertes agrégé (SCRUM-96).

    Complète `ReturnReportView`, qui ne couvre qu'une réservation : ici on
    agrège tous les incidents, avec ventilation par article et par réservation.
    """

    @pytest.mark.django_db
    def test_rapport_agrege(self, factory, magasinier, ligne):
        for incident_type, qty, facture in [
            (ReturnIncidentType.MISSING, 1, True),
            (ReturnIncidentType.MISSING, 1, False),
            (ReturnIncidentType.BROKEN, 1, False),
            (ReturnIncidentType.DESTROYED, 1, True),
        ]:
            ReturnIncident.objects.create(
                line=ligne,
                type=incident_type,
                qty=qty,
                bill_client=facture,
                reported_by=magasinier,
            )

        request = factory.get(LOSS_REPORT_URL)
        force_authenticate(request, user=magasinier)

        response = ReturnLossReportView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 4
        assert response.data["total_missing"] == 2
        assert response.data["total_broken"] == 1
        assert response.data["total_destroyed"] == 1
        assert response.data["total_billed"] == 2

        par_article = response.data["by_part"][0]

        assert par_article["part_name"] == "Tente 4 places"
        assert par_article["missing"] == 2
        assert par_article["broken"] == 1
        assert par_article["destroyed"] == 1
        assert par_article["billed"] == 2

        par_reservation = response.data["by_reservation"][0]

        assert par_reservation["reservation_numero"] == ligne.reservation.numero
        assert par_reservation["missing"] == 2

    @pytest.mark.django_db
    def test_rapport_vide(self, factory, magasinier):
        request = factory.get(LOSS_REPORT_URL)
        force_authenticate(request, user=magasinier)

        response = ReturnLossReportView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0
        assert response.data["total_missing"] == 0
        assert response.data["by_part"] == []
        assert response.data["by_reservation"] == []

    @pytest.mark.django_db
    def test_filtre_par_reservation(self, factory, magasinier, ligne):
        ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.MISSING,
            qty=1,
            reported_by=magasinier,
        )

        request = factory.get(LOSS_REPORT_URL, {"reservation": ligne.reservation_id})
        force_authenticate(request, user=magasinier)
        avec = ReturnLossReportView.as_view()(request)

        autre = factory.get(LOSS_REPORT_URL, {"reservation": ligne.reservation_id + 99})
        force_authenticate(autre, user=magasinier)
        sans = ReturnLossReportView.as_view()(autre)

        assert avec.data["count"] == 1
        assert sans.data["count"] == 0

    @pytest.mark.django_db
    def test_casse_facture_compte_dans_le_total(self, factory, magasinier, ligne):
        """Le total « facturé » se réconcilie avec les ventilations.

        « Facturé » ne dépend pas du type : un cassé refacturé doit peser dans
        `total_billed` comme dans `by_part` / `by_reservation`.
        """

        ReturnIncident.objects.create(
            line=ligne,
            type=ReturnIncidentType.BROKEN,
            qty=2,
            bill_client=True,
            reported_by=magasinier,
        )

        request = factory.get(LOSS_REPORT_URL)
        force_authenticate(request, user=magasinier)

        response = ReturnLossReportView.as_view()(request)

        assert response.data["total_billed"] == 2
        assert response.data["by_part"][0]["billed"] == 2
        assert response.data["by_reservation"][0]["billed"] == 2

    @pytest.mark.django_db
    def test_filtre_non_entier_refuse(self, factory, magasinier):
        request = factory.get(LOSS_REPORT_URL, {"reservation": "abc"})
        force_authenticate(request, user=magasinier)

        response = ReturnLossReportView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_lecture_ouverte_aux_roles_plugin(self, factory, gestionnaire):
        """C'est un rapport de gestion : la lecture suit `RoleBasedPermission`.

        Le magasinier constate les pertes, le gestionnaire les regarde — seule
        l'écriture des incidents reste réservée au magasinier et à l'admin.
        """

        request = factory.get(LOSS_REPORT_URL)
        force_authenticate(request, user=gestionnaire)

        response = ReturnLossReportView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.django_db
    def test_sans_role_plugin_refuse(self, factory, db):
        sans_role = User.objects.create_user(username="badaud", password="pwd12345")

        request = factory.get(LOSS_REPORT_URL)
        force_authenticate(request, user=sans_role)

        response = ReturnLossReportView.as_view()(request)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_bill_client_par_defaut_a_false(self, factory, magasinier, ligne):
        """Créé par l'API sans le champ, un incident n'est pas facturé."""

        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.MISSING,
            "qty": 1,
            "comment": "",
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)
        creation = ReturnIncidentListCreateView.as_view()(request)

        assert creation.status_code == status.HTTP_201_CREATED
        assert creation.data["bill_client"] is False

    @pytest.mark.django_db
    def test_bill_client_posable_a_la_creation(self, factory, magasinier, ligne):
        payload = {
            "line": ligne.pk,
            "type": ReturnIncidentType.MISSING,
            "qty": 1,
            "comment": "",
            "bill_client": True,
        }
        request = factory.post(INCIDENTS_URL, payload, format="json")
        force_authenticate(request, user=magasinier)
        creation = ReturnIncidentListCreateView.as_view()(request)

        assert creation.status_code == status.HTTP_201_CREATED
        assert creation.data["bill_client"] is True
        assert ReturnIncident.objects.get(pk=creation.data["id"]).bill_client is True
