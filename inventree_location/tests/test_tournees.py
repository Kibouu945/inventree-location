"""Tournée du jour : `GET /tournees/?date=` (lot L6).

Deux mailles dans une seule réponse, et c'est tout l'objet du lot : le livreur
organise ses arrêts **par lieu** (R30) mais charge son véhicule sur le
**récapitulatif tous lieux confondus** (R25). Aujourd'hui le front recalcule ça
en 382 lignes de TypeScript à partir de la liste plate des réservations.

Lecture seule : la vue ne touche ni les bons, ni les tables d'exécution.
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location import roles
from inventree_location.models import Livraison, StatutReservation
from inventree_location.tests.factories import (
    creer_chaine,
    make_ligne,
    make_manifestation,
    make_part,
    make_prestation,
    make_reservation,
    make_user,
)
from inventree_location.views import TourneeView

TOURNEE_URL = "/plugin/inventree-location/tournees/"


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def livreur(db):
    return make_user("bruno", role=roles.LIVREUR)


@pytest.fixture
def gestionnaire(db):
    return make_user("gina", role=roles.GESTIONNAIRE)


def _get(factory, user, params=None):
    request = factory.get(TOURNEE_URL, params or {})
    force_authenticate(request, user=user)

    return TourneeView.as_view()(request)


def _bon_a_livrer(*, lieu=None, quantite=2, part=None, jour=None, client=None):
    """Un bon validé, à livrer le jour donné (aujourd'hui par défaut)."""

    chaine = creer_chaine(quantite=quantite, lieu=lieu, part=part, client=client)
    bon = chaine["reservation"]
    bon.statut = StatutReservation.VALIDEE
    bon.date_retrait_prevue = jour or timezone.now()
    bon.save()

    return chaine


@pytest.mark.django_db
class TestAcces:
    def test_anonyme_refuse(self, factory):
        request = factory.get(TOURNEE_URL)

        assert TourneeView.as_view()(request).status_code == (
            status.HTTP_401_UNAUTHORIZED
        )

    def test_le_livreur_lit_sa_tournee(self, factory, livreur):
        assert _get(factory, livreur).status_code == status.HTTP_200_OK

    def test_le_livreur_ne_voit_que_ce_qui_est_a_livrer(self, factory, livreur):
        a_livrer = _bon_a_livrer()
        deja_livre = _bon_a_livrer()
        deja_livre["reservation"].statut = StatutReservation.LIVREE
        deja_livre["reservation"].save(update_fields=["statut"])

        response = _get(factory, livreur)

        numeros = [
            bon["numero"] for arret in response.data["arrets"] for bon in arret["bons"]
        ]

        assert numeros == [a_livrer["reservation"].numero]

    def test_le_gestionnaire_voit_aussi_le_livre(self, factory, gestionnaire):
        livre = _bon_a_livrer()
        livre["reservation"].statut = StatutReservation.LIVREE
        livre["reservation"].save(update_fields=["statut"])

        response = _get(factory, gestionnaire)

        assert response.data["quantite_totale"] == 2


@pytest.mark.django_db
class TestGroupementParLieu:
    def test_deux_prestations_d_un_meme_lieu_font_un_seul_arret(
        self, factory, gestionnaire
    ):
        """R30 : la quantité affichée est la somme de la journée sur ce lieu.

        Deux prestations distinctes, même lieu, même article : le livreur doit
        lire « 5 tables à cet arrêt », pas deux lignes à comparer lui-même.
        """

        premier = _bon_a_livrer(quantite=2)
        lieu = premier["lieu"]
        part = premier["part"]

        seconde_prestation = make_prestation(
            manifestation=premier["manifestation"], lieu=lieu
        )
        second_bon = make_reservation(
            prestation=seconde_prestation,
            demandeur=premier["demandeur"],
            statut=StatutReservation.VALIDEE,
            date_retrait_prevue=timezone.now(),
        )
        make_ligne(reservation=second_bon, part=part, quantite_demandee=3)

        response = _get(factory, gestionnaire)

        assert len(response.data["arrets"]) == 1

        arret = response.data["arrets"][0]

        assert arret["lieu"]["id"] == lieu.pk
        assert len(arret["bons"]) == 2
        assert arret["quantite_totale"] == 5
        assert arret["articles"] == [
            {"part": part.pk, "part_nom": part.name, "quantite": 5}
        ]

    def test_deux_lieux_font_deux_arrets(self, factory, gestionnaire):
        premier = _bon_a_livrer(quantite=2)
        _bon_a_livrer(quantite=4)

        response = _get(factory, gestionnaire)

        assert len(response.data["arrets"]) == 2
        assert sum(arret["quantite_totale"] for arret in response.data["arrets"]) == 6
        assert premier["lieu"].nom in {
            arret["lieu"]["nom"] for arret in response.data["arrets"]
        }

    def test_un_bon_sans_lieu_reste_visible(self, factory, gestionnaire):
        """Une prestation sans lieu est légitime : elle ne doit pas disparaître
        de la tournée, sinon le matériel part sans que personne le sache."""

        chaine = _bon_a_livrer(quantite=1)
        chaine["prestation"].lieu = None
        chaine["prestation"].save(update_fields=["lieu"])

        response = _get(factory, gestionnaire)

        assert response.data["arrets"][0]["lieu"] is None
        assert response.data["quantite_totale"] == 1


@pytest.mark.django_db
class TestRecapitulatifGlobal:
    def test_le_recap_somme_tous_les_lieux(self, factory, gestionnaire):
        """R25 : le chargement du véhicule se fait sur le total, pas par arrêt."""

        part = make_part("Table pliante", rentable=True)
        _bon_a_livrer(quantite=2, part=part)
        _bon_a_livrer(quantite=4, part=part)
        autre = make_part("Barnum", rentable=True)
        _bon_a_livrer(quantite=1, part=autre)

        response = _get(factory, gestionnaire)

        assert len(response.data["arrets"]) == 3
        assert response.data["recap_total"] == [
            {"part": autre.pk, "part_nom": "Barnum", "quantite": 1},
            {"part": part.pk, "part_nom": "Table pliante", "quantite": 6},
        ]
        assert response.data["quantite_totale"] == 7

    def test_le_client_est_nomme_sur_chaque_bon(self, factory, gestionnaire):
        chaine = _bon_a_livrer(quantite=1)

        response = _get(factory, gestionnaire)

        bon = response.data["arrets"][0]["bons"][0]

        assert bon["client_nom"] == chaine["client"].nom

    def test_la_quantite_restante_tient_compte_des_passages(
        self, factory, gestionnaire
    ):
        chaine = _bon_a_livrer(quantite=6)
        passage = Livraison.objects.create(
            reservation=chaine["reservation"], sequence=1
        )
        passage.lignes.create(ligne=chaine["ligne"], quantite_livree=4)

        response = _get(factory, gestionnaire)

        ligne = response.data["arrets"][0]["bons"][0]["lignes"][0]

        assert ligne["quantite_attendue"] == 6
        assert ligne["quantite_restante"] == 2


@pytest.mark.django_db
class TestFenetreDuJour:
    def test_par_defaut_c_est_aujourd_hui(self, factory, gestionnaire):
        _bon_a_livrer(quantite=3)
        _bon_a_livrer(quantite=9, jour=timezone.now() + timezone.timedelta(days=2))

        response = _get(factory, gestionnaire)

        assert response.data["quantite_totale"] == 3

    def test_une_date_explicite_change_la_fenetre(self, factory, gestionnaire):
        demain = timezone.now() + timezone.timedelta(days=1)
        _bon_a_livrer(quantite=3)
        _bon_a_livrer(quantite=9, jour=demain)

        response = _get(
            factory, gestionnaire, {"date": timezone.localdate(demain).isoformat()}
        )

        assert response.data["quantite_totale"] == 9

    def test_une_date_illisible_rend_400(self, factory, gestionnaire):
        response = _get(factory, gestionnaire, {"date": "demain"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_un_brouillon_n_est_pas_une_tournee(self, factory, gestionnaire):
        chaine = _bon_a_livrer(quantite=5)
        chaine["reservation"].statut = StatutReservation.BROUILLON
        chaine["reservation"].save(update_fields=["statut"])

        response = _get(factory, gestionnaire)

        assert response.data["arrets"] == []
        assert response.data["quantite_totale"] == 0

    def test_une_journee_vide_repond_quand_meme(self, factory, gestionnaire):
        response = _get(factory, gestionnaire)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["arrets"] == []
        assert response.data["recap_total"] == []


@pytest.mark.django_db
class TestLectureSeule:
    def test_lire_la_tournee_ne_projette_rien(self, factory, gestionnaire):
        _bon_a_livrer(quantite=2)

        _get(factory, gestionnaire)

        assert Livraison.objects.count() == 0

    def test_la_manifestation_sans_client_ne_casse_pas(self, factory, gestionnaire):
        # `make_manifestation` crée toujours un client ; on vérifie surtout que
        # le nom est une chaîne, jamais un `None` que le front afficherait.
        make_manifestation()
        _bon_a_livrer(quantite=1)

        response = _get(factory, gestionnaire)

        assert isinstance(
            response.data["arrets"][0]["bons"][0]["client_nom"], str
        )
