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
    Lieu,
    Prestation,
    Reservation,
    StatutReservation,
)
from inventree_location.views import BonRamassageView, RamassageListView
from inventree_location.tests.factories import make_manifestation

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
    manifestation = make_manifestation(
        nom="Camp d'été",
        date_debut=timezone.now(),
        date_fin=timezone.now(),
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

    def test_date_to_couvre_la_journee_entiere(self, factory, user, reservation):
        """Un ramassage prévu à 16 h le 10 doit sortir sur un filtre « le 10 »."""

        reservation.date_retour_prevue = "2026-09-10T16:00:00Z"
        reservation.save(update_fields=["date_retour_prevue"])

        response = _get(factory, user, date_from="2026-09-10", date_to="2026-09-10")

        assert response.data["count"] == 1

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


class TestRamassageRoles:
    """Un livreur pur ne voit que les réservations validées (cf. roles.py)."""

    @pytest.fixture
    def livreur(self, db):
        from django.contrib.auth.models import Group

        from inventree_location import roles

        account = User.objects.create_user(username="dave", password="pwd12345")
        account.groups.add(Group.objects.get(name=roles.LIVREUR))
        return account

    def test_livreur_voit_la_reservation_validee(self, factory, livreur, reservation):
        assert _get(factory, livreur).data["count"] == 1

    def test_livreur_ne_voit_pas_un_brouillon(self, factory, livreur, reservation):
        reservation.statut = StatutReservation.BROUILLON
        reservation.save(update_fields=["statut"])

        assert _get(factory, livreur).data["count"] == 0

    def test_livreur_ne_peut_pas_imprimer_le_bon_dun_brouillon(
        self, factory, livreur, reservation
    ):
        reservation.statut = StatutReservation.BROUILLON
        reservation.save(update_fields=["statut"])

        request = factory.get(f"{RAMASSAGES_URL}{reservation.pk}/bon/")
        force_authenticate(request, user=livreur)

        response = BonRamassageView.as_view()(request, pk=reservation.pk)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_gestionnaire_voit_le_brouillon(self, factory, user, reservation):
        reservation.statut = StatutReservation.BROUILLON
        reservation.save(update_fields=["statut"])

        assert _get(factory, user).data["count"] == 1


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


class TestPerimetreDuRamassage:
    """Un article virtuel n'a rien à faire revenir (CDC V06 / RET-04)."""

    @pytest.fixture
    def part_physique(self, db):
        from part.models import Part

        from inventree_location.models import RentableItem

        article = Part.objects.create(name="Tente 4 places")
        RentableItem.objects.create(part=article, is_virtual=False)
        return article

    @pytest.fixture
    def part_virtuelle(self, db):
        from part.models import Part

        from inventree_location.models import RentableItem

        article = Part.objects.create(name="Prestation montage", virtual=True)
        RentableItem.objects.create(part=article, is_virtual=True)
        return article

    @pytest.fixture
    def lignes(self, db, reservation, part_physique, part_virtuelle):
        from inventree_location.models import LigneReservation

        physique = LigneReservation.objects.create(
            reservation=reservation,
            part=part_physique,
            quantite_demandee=6,
            quantite_livree=6,
        )
        virtuelle = LigneReservation.objects.create(
            reservation=reservation,
            part=part_virtuelle,
            quantite_demandee=1,
            quantite_livree=1,
        )
        return physique, virtuelle

    def test_la_liste_ne_compte_que_le_physique(self, factory, user, lignes):
        response = _get(factory, user)

        ligne = response.data["results"][0]

        # 2 lignes en base, 1 seule à ramasser.
        assert ligne["nb_objets"] == 1
        assert ligne["quantite_totale"] == 6

    def test_le_bon_nexpose_que_le_physique(self, factory, user, reservation, lignes):
        request = factory.get(f"{RAMASSAGES_URL}{reservation.pk}/bon/")
        force_authenticate(request, user=user)

        response = BonRamassageView.as_view()(request, pk=reservation.pk)

        noms = [ligne["part_nom"] for ligne in response.data["reservation"]["lignes"]]

        assert noms == ["Tente 4 places"]

    def test_une_part_sans_extension_reste_ramassable(
        self, factory, user, reservation
    ):
        """Pas d'extension louable = pas virtuel : on ne l'écarte pas."""

        from part.models import Part

        from inventree_location.models import LigneReservation

        orpheline = Part.objects.create(name="Sans extension")
        LigneReservation.objects.create(
            reservation=reservation,
            part=orpheline,
            quantite_demandee=2,
            quantite_livree=2,
        )

        assert _get(factory, user).data["results"][0]["nb_objets"] == 1
