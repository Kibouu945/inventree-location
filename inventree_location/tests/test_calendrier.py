"""Calendrier mensuel des réservations (DIS-01).

Passe par le routeur réel : c'est FullCalendar qui appelle cet endpoint à
chaque changement de mois, avec les bornes de la fenêtre affichée.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from inventree_location import roles
from inventree_location.calendrier import STATUT_COULEURS, couleur_statut
from inventree_location.models import (
    Groupe,
    Lieu,
    Manifestation,
    Prestation,
    Reservation,
    StatutReservation,
)

User = get_user_model()

URL = "/plugin/inventree-location/reservations/calendar/"

pytestmark = [pytest.mark.django_db, pytest.mark.urls("tests.functional_urls")]


def client_for(role, username="u"):
    user = User.objects.create_user(username=username, password="pwd12345")

    if role is not None:
        user.groups.add(Group.objects.get(name=role))

    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}"
    )

    return client, user


@pytest.fixture
def prestation(db):
    organisateur = User.objects.create_user(
        username="org", password="pwd12345", first_name="Ora", last_name="Nisatrice"
    )
    groupe = Groupe.objects.create(nom="Groupe A", code="GA")
    manifestation = Manifestation.objects.create(
        nom="Camp d'été",
        date_debut="2026-06-01T00:00:00Z",
        date_fin="2026-06-30T00:00:00Z",
        statut="planifiee",
        organisateur=organisateur,
        groupe=groupe,
    )
    lieu = Lieu.objects.create(nom="Chalet", adresse="1 rue du Camp")

    return Prestation.objects.create(
        manifestation=manifestation,
        nom="Installation",
        lieu=lieu,
        date_debut="2026-06-10T00:00:00Z",
        date_fin="2026-06-12T00:00:00Z",
    )


def _reservation(prestation, *, statut, retrait, retour, demandeur=None):
    return Reservation.objects.create(
        prestation=prestation,
        demandeur=demandeur
        or User.objects.create_user(
            username=f"d{Reservation.objects.count()}", password="pwd12345"
        ),
        statut=statut,
        date_retrait_prevue=retrait,
        date_retour_prevue=retour,
    )


class TestCalendrier:
    def test_un_evenement_par_reservation(self, prestation):
        reservation = _reservation(
            prestation,
            statut=StatutReservation.VALIDEE,
            retrait="2026-06-10T08:00:00Z",
            retour="2026-06-12T18:00:00Z",
        )
        client, _ = client_for(roles.GESTIONNAIRE, "gina")

        response = client.get(URL)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

        event = response.data[0]
        assert event["id"] == str(reservation.pk)
        assert event["title"] == f"{reservation.numero} — Installation"
        assert event["start"].startswith("2026-06-10")
        assert event["end"].startswith("2026-06-12")
        assert event["color"] == STATUT_COULEURS[StatutReservation.VALIDEE]
        assert event["extendedProps"]["statut"] == "Validée"
        assert event["extendedProps"]["statut_code"] == StatutReservation.VALIDEE
        assert event["extendedProps"]["manifestation"] == "Camp d'été"
        assert event["extendedProps"]["lieu"] == "Chalet"

    def test_la_fenetre_retient_ce_qui_la_chevauche(self, prestation):
        dedans = _reservation(
            prestation,
            statut=StatutReservation.VALIDEE,
            retrait="2026-06-10T08:00:00Z",
            retour="2026-06-12T18:00:00Z",
        )
        # Commencée avant la fenêtre mais toujours en cours pendant : elle doit
        # rester visible, c'est tout l'intérêt d'un calendrier.
        a_cheval = _reservation(
            prestation,
            statut=StatutReservation.LIVREE,
            retrait="2026-05-25T08:00:00Z",
            retour="2026-06-03T18:00:00Z",
        )
        _reservation(
            prestation,
            statut=StatutReservation.VALIDEE,
            retrait="2026-08-01T08:00:00Z",
            retour="2026-08-05T18:00:00Z",
        )
        client, _ = client_for(roles.GESTIONNAIRE, "gina")

        response = client.get(URL, {"from": "2026-06-01", "to": "2026-06-30"})

        ids = {event["id"] for event in response.data}
        assert ids == {str(dedans.pk), str(a_cheval.pk)}

    def test_la_borne_de_fin_couvre_la_journee_entiere(self, prestation):
        du_jour = _reservation(
            prestation,
            statut=StatutReservation.VALIDEE,
            retrait="2026-06-30T09:00:00Z",
            retour="2026-07-02T18:00:00Z",
        )
        client, _ = client_for(roles.GESTIONNAIRE, "gina")

        response = client.get(URL, {"from": "2026-06-01", "to": "2026-06-30"})

        assert [event["id"] for event in response.data] == [str(du_jour.pk)]

    def test_un_brouillon_sans_dates_retombe_sur_la_prestation(self, prestation):
        brouillon = _reservation(
            prestation,
            statut=StatutReservation.BROUILLON,
            retrait=None,
            retour=None,
        )
        client, _ = client_for(roles.GESTIONNAIRE, "gina")

        response = client.get(URL, {"from": "2026-06-01", "to": "2026-06-30"})

        event = response.data[0]
        assert event["id"] == str(brouillon.pk)
        assert event["start"].startswith("2026-06-10")
        assert event["end"].startswith("2026-06-12")

    def test_les_reservations_archivees_sont_ecartees(self, prestation):
        archivee = _reservation(
            prestation,
            statut=StatutReservation.CLOTUREE,
            retrait="2026-06-10T08:00:00Z",
            retour="2026-06-12T18:00:00Z",
        )
        archivee.is_archived = True
        archivee.save(update_fields=["is_archived"])
        client, _ = client_for(roles.GESTIONNAIRE, "gina")

        assert client.get(URL).data == []

    def test_le_livreur_ne_voit_que_les_validees(self, prestation):
        validee = _reservation(
            prestation,
            statut=StatutReservation.VALIDEE,
            retrait="2026-06-10T08:00:00Z",
            retour="2026-06-12T18:00:00Z",
        )
        _reservation(
            prestation,
            statut=StatutReservation.BROUILLON,
            retrait="2026-06-10T08:00:00Z",
            retour="2026-06-12T18:00:00Z",
        )
        client, _ = client_for(roles.LIVREUR, "lucie")

        response = client.get(URL)

        assert [event["id"] for event in response.data] == [str(validee.pk)]

    def test_les_evenements_sont_tries_par_debut(self, prestation):
        tard = _reservation(
            prestation,
            statut=StatutReservation.VALIDEE,
            retrait="2026-06-20T08:00:00Z",
            retour="2026-06-22T18:00:00Z",
        )
        tot = _reservation(
            prestation,
            statut=StatutReservation.VALIDEE,
            retrait="2026-06-02T08:00:00Z",
            retour="2026-06-04T18:00:00Z",
        )
        client, _ = client_for(roles.GESTIONNAIRE, "gina")

        response = client.get(URL)

        assert [event["id"] for event in response.data] == [str(tot.pk), str(tard.pk)]

    def test_un_anonyme_est_rejete(self, prestation):
        assert APIClient().get(URL).status_code == status.HTTP_401_UNAUTHORIZED

    def test_un_compte_sans_role_est_interdit(self, prestation):
        client, _ = client_for(None, "norole")

        assert client.get(URL).status_code == status.HTTP_403_FORBIDDEN


class TestPalette:
    def test_chaque_statut_a_sa_couleur(self):
        assert set(STATUT_COULEURS) == set(StatutReservation.values)

    def test_un_statut_inconnu_retombe_sur_le_gris(self):
        assert couleur_statut("inexistant") == "#868e96"
