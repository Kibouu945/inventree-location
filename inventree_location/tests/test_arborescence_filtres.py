"""Filtres alimentant l'arborescence de la maquette « Manifestation » :
``periode`` sur les manifestations, ``prestation`` sur les réservations.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location import roles
from inventree_location.models import (
    Groupe,
    Manifestation,
    Prestation,
    Reservation,
    StatutManifestation,
)
from inventree_location.views import (
    ManifestationListCreateView,
    ReservationListCreateView,
)

User = get_user_model()

MANIFESTATIONS_URL = "/plugin/inventree-location/manifestations/"
RESERVATIONS_URL = "/plugin/inventree-location/reservations/"


@pytest.fixture
def gestionnaire(db):
    user = User.objects.create_user(username="gest", password="pwd12345")
    groupe, _ = Group.objects.get_or_create(name=roles.GESTIONNAIRE)
    user.groups.add(groupe)
    return user


@pytest.fixture
def appel(gestionnaire):
    """Appelle une vue directement : pas d'URLConf sous pytest, `core.py` n'y
    est pas importable."""

    factory = APIRequestFactory()

    def appeler(vue, url, params=None):
        requete = factory.get(url, params or {})
        force_authenticate(requete, user=gestionnaire)
        return vue.as_view()(requete)

    return appeler


@pytest.fixture
def groupe(db):
    return Groupe.objects.create(nom="Jambville", code="JAM")


def _manifestation(nom, groupe, user, jours_depuis_aujourdhui):
    """Manifestation dont la fin tombe à `jours` de la date du jour (locale)."""

    fin = timezone.localtime() + timedelta(days=jours_depuis_aujourdhui)

    return Manifestation.objects.create(
        nom=nom,
        date_debut=fin - timedelta(days=1),
        date_fin=fin,
        statut=StatutManifestation.PLANIFIEE,
        organisateur=user,
        groupe=groupe,
    )


@pytest.mark.django_db
class TestFiltrePeriodeManifestation:
    def test_futur_garde_celles_qui_ne_sont_pas_terminees(
        self, appel, groupe, gestionnaire
    ):
        _manifestation("Ancienne", groupe, gestionnaire, -10)
        _manifestation("Prochaine", groupe, gestionnaire, 10)

        reponse = appel(
            ManifestationListCreateView, MANIFESTATIONS_URL, {"periode": "futur"}
        )

        assert [m["nom"] for m in reponse.data["results"]] == ["Prochaine"]

    def test_passe_garde_celles_qui_sont_terminees(
        self, appel, groupe, gestionnaire
    ):
        _manifestation("Ancienne", groupe, gestionnaire, -10)
        _manifestation("Prochaine", groupe, gestionnaire, 10)

        reponse = appel(
            ManifestationListCreateView, MANIFESTATIONS_URL, {"periode": "passe"}
        )

        assert [m["nom"] for m in reponse.data["results"]] == ["Ancienne"]

    def test_celle_qui_finit_aujourdhui_est_a_venir(
        self, appel, groupe, gestionnaire
    ):
        # Découpage sur la date de fin : elle a encore ses ramassages devant.
        _manifestation("Aujourd'hui", groupe, gestionnaire, 0)

        reponse = appel(
            ManifestationListCreateView, MANIFESTATIONS_URL, {"periode": "futur"}
        )

        assert [m["nom"] for m in reponse.data["results"]] == ["Aujourd'hui"]

    @pytest.mark.parametrize("valeur", ["tout", "", "n_importe_quoi"])
    def test_toute_autre_valeur_ne_filtre_rien(
        self, appel, groupe, gestionnaire, valeur
    ):
        """« Tout » = pas de filtre ; une valeur inconnue est du bruit."""

        _manifestation("Ancienne", groupe, gestionnaire, -10)
        _manifestation("Prochaine", groupe, gestionnaire, 10)

        reponse = appel(
            ManifestationListCreateView, MANIFESTATIONS_URL, {"periode": valeur}
        )

        assert reponse.data["count"] == 2


@pytest.mark.django_db
class TestFiltrePrestationReservation:
    def test_ne_renvoie_que_les_bons_de_la_prestation_demandee(
        self, appel, groupe, gestionnaire
    ):
        manifestation = _manifestation("Camp", groupe, gestionnaire, 10)
        debut = manifestation.date_debut
        fin = manifestation.date_fin

        premiere = Prestation.objects.create(
            manifestation=manifestation, nom="Zone A", date_debut=debut, date_fin=fin
        )
        seconde = Prestation.objects.create(
            manifestation=manifestation, nom="Zone B", date_debut=debut, date_fin=fin
        )

        attendue = Reservation.objects.create(
            prestation=premiere, demandeur=gestionnaire, date_demande=debut
        )
        Reservation.objects.create(
            prestation=seconde, demandeur=gestionnaire, date_demande=debut
        )

        reponse = appel(
            ReservationListCreateView, RESERVATIONS_URL, {"prestation": premiere.pk}
        )

        assert [r["id"] for r in reponse.data["results"]] == [attendue.pk]

    def test_sans_le_filtre_tous_les_bons_remontent(
        self, appel, groupe, gestionnaire
    ):
        manifestation = _manifestation("Camp", groupe, gestionnaire, 10)
        prestation = Prestation.objects.create(
            manifestation=manifestation,
            nom="Zone A",
            date_debut=manifestation.date_debut,
            date_fin=manifestation.date_fin,
        )
        Reservation.objects.create(
            prestation=prestation,
            demandeur=gestionnaire,
            date_demande=manifestation.date_debut,
        )
        Reservation.objects.create(
            prestation=prestation,
            demandeur=gestionnaire,
            date_demande=manifestation.date_debut,
        )

        reponse = appel(ReservationListCreateView, RESERVATIONS_URL)

        assert reponse.data["count"] == 2
