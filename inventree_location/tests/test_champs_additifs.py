"""Champs ajoutés par le lot L1, et la reprise de statut qui l'accompagne."""

from __future__ import annotations

from decimal import Decimal

import pytest

from importlib import import_module

from django.apps import apps as registre
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location import roles
from inventree_location.models import (
    RentableItem,
    Reservation,
    StatutManifestation,
    StatutPrestation,
    StatutReservation,
)
from inventree_location.tests.factories import (
    make_lieu,
    make_manifestation,
    make_part,
    make_prestation,
    make_reservation,
    make_user,
)
from inventree_location.views import PrestationListCreateView

# Le nom du module commence par un chiffre : `import_module` est le seul moyen.
migration_0025 = import_module(
    "inventree_location.migrations.0025_statut_des_prestations_existantes"
)

PRESTATIONS_URL = "/plugin/inventree-location/prestations/"


@pytest.mark.django_db
class TestDefauts:
    def test_le_poids_est_inconnu_et_non_zero(self):
        """« 0 kg » fausserait une somme de chargement ; « inconnu » ne dit rien."""

        part = make_part(rentable=True)

        assert RentableItem.objects.get(part=part).poids is None

    def test_une_prestation_naît_en_brouillon(self):
        prestation = make_prestation()

        assert prestation.statut == StatutPrestation.BROUILLON
        assert prestation.modifie_apres_devis is False

    def test_la_manifestation_naît_sans_couleur_et_sans_remise(self):
        manifestation = make_manifestation()

        assert manifestation.couleur == ""
        assert manifestation.pourcent_remise_globale == Decimal("0")

    def test_un_lieu_naît_sans_description(self):
        assert make_lieu().description == ""

    def test_les_statuts_modifiables_sont_le_brouillon_et_le_planifie(self):
        assert StatutPrestation.modifiables() == (
            StatutPrestation.BROUILLON,
            StatutPrestation.PLANIFIEE,
        )


@pytest.mark.django_db
class TestLieuObligatoireHorsBrouillon:
    """Le lieu reste nullable en base, mais une prestation sans lieu est
    invisible des tournées : elle ne quitte pas le brouillon."""

    def _poster(self, payload):
        requete = APIRequestFactory().post(PRESTATIONS_URL, payload, format="json")
        force_authenticate(requete, user=make_user(role=roles.GESTIONNAIRE))
        return PrestationListCreateView.as_view()(requete)

    def _payload(self, manifestation, **extra):
        return {
            "nom": "Zone technique",
            "manifestation": manifestation.pk,
            "date_debut": manifestation.date_debut.isoformat(),
            "date_fin": manifestation.date_fin.isoformat(),
            **extra,
        }

    def test_un_brouillon_sans_lieu_est_accepte(self):
        manifestation = make_manifestation()

        reponse = self._poster(self._payload(manifestation))

        assert reponse.status_code == 201
        assert reponse.data["lieu"] is None

    def test_planifier_sans_lieu_est_refuse(self):
        manifestation = make_manifestation()

        reponse = self._poster(
            self._payload(manifestation, statut=StatutPrestation.PLANIFIEE)
        )

        assert reponse.status_code == 400
        assert "lieu" in reponse.data

    def test_planifier_avec_un_lieu_passe(self):
        manifestation = make_manifestation()

        reponse = self._poster(
            self._payload(
                manifestation,
                statut=StatutPrestation.PLANIFIEE,
                lieu=make_lieu().pk,
            )
        )

        assert reponse.status_code == 201
        assert reponse.data["statut"] == StatutPrestation.PLANIFIEE


@pytest.mark.django_db
class TestRepriseDesStatuts:
    """La migration `0025` donne un statut aux prestations déjà en base."""

    def _promouvoir(self):
        migration_0025.promouvoir(registre, None)

    def test_une_prestation_sans_reservation_reste_en_brouillon(self):
        prestation = make_prestation()

        self._promouvoir()
        prestation.refresh_from_db()

        assert prestation.statut == StatutPrestation.BROUILLON

    @pytest.mark.parametrize(
        "statut_reservation",
        [
            StatutReservation.VALIDEE,
            StatutReservation.LIVREE,
            StatutReservation.RETOURNEE,
            StatutReservation.CLOTUREE,
        ],
    )
    def test_une_reservation_engagee_confirme_la_prestation(self, statut_reservation):
        prestation = make_prestation()
        make_reservation(prestation=prestation, statut=statut_reservation)

        self._promouvoir()
        prestation.refresh_from_db()

        assert prestation.statut == StatutPrestation.CONFIRMEE

    def test_une_reservation_en_brouillon_n_engage_rien(self):
        prestation = make_prestation()
        make_reservation(prestation=prestation, statut=StatutReservation.BROUILLON)

        self._promouvoir()
        prestation.refresh_from_db()

        assert prestation.statut == StatutPrestation.BROUILLON

    def test_une_manifestation_annulee_annule_ses_prestations(self):
        manifestation = make_manifestation(statut=StatutManifestation.ANNULEE)
        prestation = make_prestation(manifestation=manifestation)
        # Même engagée : l'annulation de la manifestation l'emporte.
        make_reservation(prestation=prestation, statut=StatutReservation.VALIDEE)

        self._promouvoir()
        prestation.refresh_from_db()

        assert prestation.statut == StatutPrestation.ANNULEE

    def test_la_reprise_est_rejouable(self):
        prestation = make_prestation()
        make_reservation(prestation=prestation, statut=StatutReservation.LIVREE)

        self._promouvoir()
        self._promouvoir()
        prestation.refresh_from_db()

        assert prestation.statut == StatutPrestation.CONFIRMEE
        assert Reservation.objects.count() == 1
