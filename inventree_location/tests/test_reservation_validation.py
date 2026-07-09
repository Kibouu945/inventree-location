"""Tests des règles métier de `ReservationSerializer.validate` (RES-03).

Brouillon : sauvegarde permissive (aucun champ obligatoire).
Soumission (statut != brouillon) : demandeur, prestation, dates, au moins une
ligne et au moins un article virtuel (RentableItem.is_virtual=True)
deviennent obligatoires, et la période doit couvrir la prestation.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location.models import (
    Groupe,
    Manifestation,
    Prestation,
    RentableItem,
)
from inventree_location.views import (
    ReservationDetailView,
    ReservationListCreateView,
)

from part.models import Part

User = get_user_model()

RESA_URL = "/plugin/inventree-location/reservations/"


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
    groupe = Groupe.objects.create(nom="Jambville", code="JAM")
    manifestation = Manifestation.objects.create(
        nom="Camp été 2026",
        date_debut=now,
        date_fin=now + timedelta(days=7),
        organisateur=user,
        groupe=groupe,
    )
    return Prestation.objects.create(
        manifestation=manifestation,
        nom="Installation",
        date_debut=now,
        date_fin=now + timedelta(hours=4),
    )


@pytest.fixture
def materiel(db):
    return Part.objects.create(name="Tente 4 places")


@pytest.fixture
def article_virtuel(db):
    part = Part.objects.create(name="Prestation nettoyage")
    RentableItem.objects.create(part=part, is_virtual=True)
    return part


class TestBrouillonPermissif:
    @pytest.mark.django_db
    def test_brouillon_sans_dates_ni_lignes_accepte(self, factory, user, prestation):
        # prestation/demandeur restent obligatoires (FK non-nullables) mais
        # dates, lignes et article virtuel sont facultatifs en brouillon.
        payload = {
            "statut": "brouillon",
            "prestation": prestation.pk,
            "demandeur": user.pk,
            "date_demande": timezone.now().isoformat(),
        }
        request = factory.post(RESA_URL, payload, format="json")
        force_authenticate(request, user=user)
        response = ReservationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED


class TestSoumissionStricte:
    @pytest.mark.django_db
    def test_refuse_sans_dates_ni_lignes(self, factory, user, prestation):
        payload = {
            "statut": "soumise",
            "prestation": prestation.pk,
            "demandeur": user.pk,
            "date_demande": timezone.now().isoformat(),
        }
        request = factory.post(RESA_URL, payload, format="json")
        force_authenticate(request, user=user)
        response = ReservationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "date_retrait_prevue" in response.data
        assert "date_retour_prevue" in response.data
        assert "lignes" in response.data

    @pytest.mark.django_db
    def test_refuse_sans_article_virtuel(
        self, factory, user, prestation, materiel
    ):
        payload = {
            "statut": "soumise",
            "prestation": prestation.pk,
            "demandeur": user.pk,
            "date_demande": timezone.now().isoformat(),
            "date_retrait_prevue": prestation.date_debut.isoformat(),
            "date_retour_prevue": prestation.date_fin.isoformat(),
            "lignes": [{"part": materiel.pk, "quantite_demandee": 2}],
        }
        request = factory.post(RESA_URL, payload, format="json")
        force_authenticate(request, user=user)
        response = ReservationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "lignes" in response.data

    @pytest.mark.django_db
    def test_refuse_periode_ne_couvrant_pas_la_prestation(
        self, factory, user, prestation, materiel, article_virtuel
    ):
        payload = {
            "statut": "soumise",
            "prestation": prestation.pk,
            "demandeur": user.pk,
            "date_demande": timezone.now().isoformat(),
            # Commence après le début de la prestation : ne couvre pas.
            "date_retrait_prevue": (
                prestation.date_debut + timedelta(hours=1)
            ).isoformat(),
            "date_retour_prevue": prestation.date_fin.isoformat(),
            "lignes": [
                {"part": materiel.pk, "quantite_demandee": 2},
                {"part": article_virtuel.pk, "quantite_demandee": 1},
            ],
        }
        request = factory.post(RESA_URL, payload, format="json")
        force_authenticate(request, user=user)
        response = ReservationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "date_retrait_prevue" in response.data

    @pytest.mark.django_db
    def test_accepte_avec_materiel_et_article_virtuel(
        self, factory, user, prestation, materiel, article_virtuel
    ):
        payload = {
            "statut": "soumise",
            "prestation": prestation.pk,
            "demandeur": user.pk,
            "date_demande": timezone.now().isoformat(),
            "date_retrait_prevue": prestation.date_debut.isoformat(),
            "date_retour_prevue": prestation.date_fin.isoformat(),
            "lignes": [
                {"part": materiel.pk, "quantite_demandee": 2},
                {"part": article_virtuel.pk, "quantite_demandee": 1},
            ],
        }
        request = factory.post(RESA_URL, payload, format="json")
        force_authenticate(request, user=user)
        response = ReservationListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["numero"]

    @pytest.mark.django_db
    def test_patch_brouillon_vers_soumise_reutilise_lignes_existantes(
        self, factory, user, prestation, materiel, article_virtuel
    ):
        from inventree_location.models import LigneReservation, Reservation

        reservation = Reservation.objects.create(
            prestation=prestation,
            demandeur=user,
            date_demande=timezone.now(),
            date_retrait_prevue=prestation.date_debut,
            date_retour_prevue=prestation.date_fin,
        )
        LigneReservation.objects.create(
            reservation=reservation, part=materiel, quantite_demandee=2
        )
        LigneReservation.objects.create(
            reservation=reservation, part=article_virtuel, quantite_demandee=1
        )

        request = factory.patch(
            f"{RESA_URL}{reservation.pk}/", {"statut": "soumise"}, format="json"
        )
        force_authenticate(request, user=user)
        response = ReservationDetailView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["statut"] == "soumise"
