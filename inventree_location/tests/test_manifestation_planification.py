"""Tests du passage « brouillon » → « planifiée » (recette 4.5.4)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location import roles
from inventree_location.models import (
    Client,
    Lieu,
    Manifestation,
    Prestation,
    StatutManifestation,
)
from inventree_location.planification import obstacles_a_la_planification
from inventree_location.views import ManifestationPlanifierView

User = get_user_model()


def _url(manifestation):
    return f"/plugin/inventree-location/manifestations/{manifestation.pk}/planifier/"


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def client(db):
    return Client.objects.create(nom="Jambville", email="jam@exemple.test")


@pytest.fixture
def lieu(db):
    return Lieu.objects.create(nom="Salle des fêtes", adresse="1 rue du Camp")


def _user(username, role):
    account = User.objects.create_user(username=username, password="pwd12345")
    account.groups.add(Group.objects.get(name=role))
    return account


@pytest.fixture
def gestionnaire(db):
    return _user("alice", roles.GESTIONNAIRE)


@pytest.fixture
def lecteur(db):
    return _user("leo", roles.LECTEUR)


@pytest.fixture
def manifestation(db, client):
    debut = timezone.now() + timedelta(days=10)
    return Manifestation.objects.create(
        nom="Camp d'été",
        date_debut=debut,
        date_fin=debut + timedelta(days=5),
        statut=StatutManifestation.BROUILLON,
        client=client,
    )


def _prestation(manifestation, lieu=None, nom="Montage"):
    return Prestation.objects.create(
        nom=nom,
        manifestation=manifestation,
        lieu=lieu,
        date_debut=manifestation.date_debut,
        date_fin=manifestation.date_fin,
    )


@pytest.mark.django_db
class TestObstacles:
    def test_brouillon_garni_est_planifiable(self, manifestation, lieu):
        _prestation(manifestation, lieu)
        assert obstacles_a_la_planification(manifestation) == []

    def test_sans_prestation_refuse(self, manifestation):
        obstacles = obstacles_a_la_planification(manifestation)
        assert len(obstacles) == 1
        assert "Aucune prestation" in obstacles[0]

    def test_prestation_sans_lieu_refuse_en_la_nommant(self, manifestation):
        _prestation(manifestation, None, nom="Montage")
        obstacles = obstacles_a_la_planification(manifestation)
        assert len(obstacles) == 1
        assert "Montage" in obstacles[0]

    def test_manifestation_terminee_refuse(self, manifestation, lieu):
        debut = timezone.now() - timedelta(days=20)
        manifestation.date_debut = debut
        manifestation.date_fin = debut + timedelta(days=2)
        manifestation.save(update_fields=["date_debut", "date_fin"])
        _prestation(manifestation, lieu)

        obstacles = obstacles_a_la_planification(manifestation)
        assert len(obstacles) == 1
        assert "terminée" in obstacles[0]

    def test_manifestation_commencee_refuse(self, manifestation, lieu):
        manifestation.date_debut = timezone.now() - timedelta(hours=2)
        manifestation.date_fin = timezone.now() + timedelta(days=2)
        manifestation.save(update_fields=["date_debut", "date_fin"])
        _prestation(manifestation, lieu)

        obstacles = obstacles_a_la_planification(manifestation)
        assert len(obstacles) == 1
        assert "commencé" in obstacles[0]

    def test_les_motifs_se_cumulent(self, manifestation):
        debut = timezone.now() - timedelta(days=20)
        manifestation.date_debut = debut
        manifestation.date_fin = debut + timedelta(days=2)
        manifestation.save(update_fields=["date_debut", "date_fin"])

        # Passée ET sans prestation : les deux motifs doivent remonter.
        assert len(obstacles_a_la_planification(manifestation)) == 2

    def test_deja_planifiee_refuse_sans_examiner_le_reste(self, manifestation):
        manifestation.statut = StatutManifestation.PLANIFIEE
        # Aucune prestation : le motif doit rester le statut, pas le contenu.
        assert obstacles_a_la_planification(manifestation) == [
            "Seule une manifestation en brouillon peut être planifiée."
        ]


@pytest.mark.django_db
class TestPlanifierView:
    def test_gestionnaire_planifie(self, factory, gestionnaire, manifestation, lieu):
        _prestation(manifestation, lieu)

        request = factory.post(_url(manifestation))
        force_authenticate(request, user=gestionnaire)
        response = ManifestationPlanifierView.as_view()(request, pk=manifestation.pk)

        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["statut"] == StatutManifestation.PLANIFIEE

        manifestation.refresh_from_db()
        assert manifestation.statut == StatutManifestation.PLANIFIEE

    def test_refus_liste_les_motifs_et_ne_change_rien(
        self, factory, gestionnaire, manifestation
    ):
        request = factory.post(_url(manifestation))
        force_authenticate(request, user=gestionnaire)
        response = ManifestationPlanifierView.as_view()(request, pk=manifestation.pk)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["obstacles"]

        manifestation.refresh_from_db()
        assert manifestation.statut == StatutManifestation.BROUILLON

    def test_get_annonce_la_planifiabilite(
        self, factory, gestionnaire, manifestation, lieu
    ):
        request = factory.get(_url(manifestation))
        force_authenticate(request, user=gestionnaire)
        response = ManifestationPlanifierView.as_view()(request, pk=manifestation.pk)

        assert response.data["planifiable"] is False

        _prestation(manifestation, lieu)

        request = factory.get(_url(manifestation))
        force_authenticate(request, user=gestionnaire)
        response = ManifestationPlanifierView.as_view()(request, pk=manifestation.pk)

        assert response.data["planifiable"] is True
        assert response.data["obstacles"] == []

    def test_lecteur_refuse(self, factory, lecteur, manifestation, lieu):
        _prestation(manifestation, lieu)

        request = factory.post(_url(manifestation))
        force_authenticate(request, user=lecteur)
        response = ManifestationPlanifierView.as_view()(request, pk=manifestation.pk)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_manifestation_inconnue(self, factory, gestionnaire):
        request = factory.post("/plugin/inventree-location/manifestations/999/planifier/")
        force_authenticate(request, user=gestionnaire)
        response = ManifestationPlanifierView.as_view()(request, pk=999)

        assert response.status_code == status.HTTP_404_NOT_FOUND
