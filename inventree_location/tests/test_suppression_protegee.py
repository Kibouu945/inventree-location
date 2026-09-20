"""Ce qui est encore référencé ne se supprime pas — et le dit.

Les clés étrangères en `PROTECT` portent une règle métier : on ne supprime pas
une manifestation qui porte des prestations, ni un lieu qui porte des
prestations. Le refus est normal ; c'est sa **forme** qui était fausse.

Django lève alors `ProtectedError`, que DRF ne sait pas traduire : la requête
ressortait en 500, journalisée comme une erreur serveur, et l'écran annonçait
une panne au lieu de dire ce qui retenait. Ces tests verrouillent le 409 et le
décompte de ce qui bloque.
"""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location import roles
from inventree_location.models import Manifestation, Prestation
from inventree_location.tests.factories import (
    make_lieu,
    make_manifestation,
    make_prestation,
    make_user,
)
from inventree_location.views import (
    LieuDetailView,
    ManifestationDetailView,
    PrestationDetailView,
)


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def admin(db):
    return make_user("admin_suppression", role=roles.ADMIN)


def _supprimer(factory, user, vue, chemin, pk):
    requete = factory.delete(chemin)
    force_authenticate(requete, user=user)
    return vue.as_view()(requete, pk=pk)


class TestSuppressionRetenue:
    """Le refus sort en 409, nommé, jamais en 500."""

    def test_une_manifestation_qui_porte_une_prestation_ne_se_supprime_pas(
        self, factory, admin
    ):
        manifestation = make_manifestation()
        make_prestation(manifestation=manifestation)

        reponse = _supprimer(
            factory, admin, ManifestationDetailView, "/manifestations/", manifestation.pk
        )

        assert reponse.status_code == status.HTTP_409_CONFLICT
        assert Manifestation.objects.filter(pk=manifestation.pk).exists()

    def test_le_refus_nomme_et_compte_ce_qui_retient(self, factory, admin):
        """Le message doit servir à agir : savoir quoi retirer d'abord."""

        manifestation = make_manifestation()
        make_prestation(manifestation=manifestation)
        make_prestation(manifestation=manifestation)

        reponse = _supprimer(
            factory, admin, ManifestationDetailView, "/manifestations/", manifestation.pk
        )

        detail = str(reponse.data["detail"])
        assert "cette manifestation" in detail
        assert "2 prestations" in detail
        assert "s'y rattachent" in detail

    def test_un_lieu_qui_porte_une_prestation_ne_se_supprime_pas(
        self, factory, admin
    ):
        lieu = make_lieu()
        make_prestation(lieu=lieu)

        reponse = _supprimer(factory, admin, LieuDetailView, "/lieux/", lieu.pk)

        assert reponse.status_code == status.HTTP_409_CONFLICT

    def test_une_prestation_libre_se_supprime_encore(self, factory, admin):
        """Le garde-fou ne doit pas interdire ce qui était permis."""

        prestation = make_prestation()

        reponse = _supprimer(
            factory, admin, PrestationDetailView, "/prestations/", prestation.pk
        )

        assert reponse.status_code == status.HTTP_204_NO_CONTENT
        assert not Prestation.objects.filter(pk=prestation.pk).exists()
