"""Tests des endpoints de ramassage (SCRUM-89).

Couvre :
- `RamassageListView` : liste, filtre `lieu`, exclusion des statuts terminés ;
- `BonRamassageView`  : bon de ramassage d'une réservation ;
- `RamassageSerializer` : le lieu exposé suit `Prestation.lieu` (ORG-02, un seul
  lieu par prestation) et vaut ``None`` quand la prestation n'en a pas.

Le champ `lieu` est testé explicitement : le code d'origine interrogeait
``prestation__lieux``, la relation inverse d'avant la migration 0008, ce qui
faisait répondre 500 à l'endpoint sans qu'aucun test ne le voie.

Même pattern que `test_lieu_views.py` : `APIRequestFactory` + `force_authenticate`.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location.models import (
    Groupe,
    Lieu,
    Manifestation,
    Prestation,
    Reservation,
    StatutReservation,
)
from inventree_location.views import BonRamassageView, RamassageListView

User = get_user_model()

RAMASSAGES_URL = "/plugin/inventree-location/ramassages/"


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
def lieu(db):
    return Lieu.objects.create(
        nom="Terrain de Jambville",
        adresse="Jambville",
        latitude="49.047395",
        longitude="1.850955",
    )


@pytest.fixture
def prestation(db, user, lieu):
    manifestation = Manifestation.objects.create(
        nom="Camp d'été",
        date_debut=timezone.now(),
        date_fin=timezone.now(),
        organisateur=user,
        groupe=Groupe.objects.create(nom="Groupe test", code="GT"),
    )

    return Prestation.objects.create(
        manifestation=manifestation,
        lieu=lieu,
        nom="Installation du campement",
        date_debut=timezone.now(),
        date_fin=timezone.now(),
    )


@pytest.fixture
def reservation(db, prestation, user):
    return Reservation.objects.create(
        numero="RES-2026-0001",
        prestation=prestation,
        demandeur=user,
        statut=StatutReservation.VALIDEE,
        date_retour_prevue=timezone.now(),
    )


def _get(factory, user, url=RAMASSAGES_URL, **params):
    request = factory.get(url, params)
    force_authenticate(request, user=user)
    return RamassageListView.as_view()(request)


class TestRamassageList:
    def test_liste_expose_le_lieu_de_la_prestation(self, factory, user, reservation):
        response = _get(factory, user)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1

        ligne = response.data["results"][0]

        assert ligne["numero"] == "RES-2026-0001"
        assert ligne["lieu"]["nom"] == "Terrain de Jambville"
        assert ligne["lieu"]["adresse"] == "Jambville"

    def test_lieu_absent_est_none(self, factory, user, reservation):
        reservation.prestation.lieu = None
        reservation.prestation.save(update_fields=["lieu"])

        response = _get(factory, user)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"][0]["lieu"] is None

    @pytest.mark.parametrize(
        "terme, attendu",
        [
            ("Jambville", 1),
            ("jambv", 1),
            ("Terrain", 1),
            ("Bordeaux", 0),
        ],
    )
    def test_filtre_lieu_sur_nom_et_adresse(
        self, factory, user, reservation, terme, attendu
    ):
        response = _get(factory, user, lieu=terme)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == attendu

    def test_sans_date_de_retour_pas_de_ramassage(self, factory, user, reservation):
        reservation.date_retour_prevue = None
        reservation.save(update_fields=["date_retour_prevue"])

        assert _get(factory, user).data["count"] == 0

    @pytest.mark.parametrize(
        "statut",
        [
            StatutReservation.ANNULEE,
            StatutReservation.REFUSEE,
            StatutReservation.CLOTUREE,
        ],
    )
    def test_statuts_termines_exclus(self, factory, user, reservation, statut):
        reservation.statut = statut
        reservation.save(update_fields=["statut"])

        assert _get(factory, user).data["count"] == 0


class TestBonRamassage:
    def test_bon_contient_le_lieu_et_les_lignes(self, factory, user, reservation):
        request = factory.get(f"{RAMASSAGES_URL}{reservation.pk}/bon/")
        force_authenticate(request, user=user)

        response = BonRamassageView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["titre"] == "Bon de ramassage RES-2026-0001"
        assert response.data["reservation"]["lieu"]["nom"] == "Terrain de Jambville"
        assert response.data["reservation"]["lignes"] == []

    def test_reservation_inconnue_renvoie_404(self, factory, user, db):
        request = factory.get(f"{RAMASSAGES_URL}9999/bon/")
        force_authenticate(request, user=user)

        response = BonRamassageView.as_view()(request, pk=9999)

        assert response.status_code == status.HTTP_404_NOT_FOUND
