"""Tests du stock réel et du SAV (SCRUM-112).

La PR #40 arrivait sans aucun test sur `sav.py` (574 lignes). On couvre ici ce
qui porte le métier :

- `get_real_available_stock` : ce qui sort du stock disponible et ce qui y
  revient (SAV ouvert, réparé, détruit, manquant) ;
- `RamassageRetourView` : la saisie du retour ventile les quantités, déduit
  l'état de la ligne, ouvre et referme les tickets, fait passer la réservation
  en « retournée » ;
- les gardes : quantités incohérentes, ligne d'une autre réservation, RBAC.

Même pattern que `test_return_incidents.py` : `APIRequestFactory` +
`force_authenticate`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from part.models import Part
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate
from stock.models import StockItem

from inventree_location import roles
from inventree_location.models import (
    Groupe,
    LigneReservation,
    Manifestation,
    Prestation,
    RentableItem,
    Reservation,
    SavTicket,
    StatutReservation,
    StatutSavTicket,
    TypeSavTicket,
)
from inventree_location.sav import (
    DestroyedItemsListView,
    RamassageRetourView,
    SavTicketDetailView,
    SavTicketListView,
    get_real_available_stock,
    get_unavailable_stock_quantity,
)

User = get_user_model()

RETOUR_URL = "/plugin/inventree-location/ramassages/{pk}/retour/"
TICKETS_URL = "/plugin/inventree-location/sav/tickets/"
DETRUITS_URL = "/plugin/inventree-location/sav/detruits/"


@pytest.fixture
def factory():
    return APIRequestFactory()


def _compte(username, role):
    account = User.objects.create_user(username=username, password="pwd12345")
    account.groups.add(Group.objects.get(name=role))
    return account


@pytest.fixture
def magasinier(db):
    return _compte("mag", roles.MAGASINIER)


@pytest.fixture
def gestionnaire(db):
    return _compte("gestion", roles.GESTIONNAIRE)


@pytest.fixture
def technicien_sav(db):
    return _compte("sav", roles.SAV)


@pytest.fixture
def part(db):
    article = Part.objects.create(name="Tente 4 places")
    RentableItem.objects.create(part=article)
    StockItem.objects.create(part=article, quantity=10)
    return article


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
        statut=StatutReservation.LIVREE,
        date_retour_prevue=now + timedelta(days=8),
    )


@pytest.fixture
def ligne(db, reservation, part):
    return LigneReservation.objects.create(
        reservation=reservation,
        part=part,
        quantite_demandee=6,
        quantite_livree=6,
    )


def _patch_retour(factory, user, reservation, payload):
    url = RETOUR_URL.format(pk=reservation.pk)
    request = factory.patch(url, payload, format="json")
    force_authenticate(request, user=user)
    return RamassageRetourView.as_view()(request, pk=reservation.pk)


class TestStockReel:
    """« Combien reste-t-il en état de servir » — hors SAV, casse et manquants."""

    @pytest.mark.django_db
    def test_sans_incident_le_stock_reel_egale_le_stock_inventree(self, part):
        assert get_unavailable_stock_quantity(part.pk) == 0
        assert get_real_available_stock(part.pk) == 10

    @pytest.mark.django_db
    def test_un_ticket_sav_ouvert_sort_du_stock(self, ligne, part, magasinier):
        SavTicket.objects.create(
            ligne_reservation=ligne,
            reservation=ligne.reservation,
            part=part,
            type_ticket=TypeSavTicket.REPARATION,
            statut=StatutSavTicket.OUVERT,
            quantite=3,
            created_by=magasinier,
        )

        assert get_unavailable_stock_quantity(part.pk) == 3
        assert get_real_available_stock(part.pk) == 7

    @pytest.mark.django_db
    def test_un_article_repare_revient_au_stock(self, ligne, part, magasinier):
        ticket = SavTicket.objects.create(
            ligne_reservation=ligne,
            reservation=ligne.reservation,
            part=part,
            type_ticket=TypeSavTicket.REPARATION,
            statut=StatutSavTicket.OUVERT,
            quantite=3,
            created_by=magasinier,
        )

        ticket.statut = StatutSavTicket.REPARE
        ticket.save(update_fields=["statut"])

        assert get_real_available_stock(part.pk) == 10

    @pytest.mark.django_db
    def test_un_article_detruit_ne_revient_jamais(self, ligne, part, magasinier):
        SavTicket.objects.create(
            ligne_reservation=ligne,
            reservation=ligne.reservation,
            part=part,
            type_ticket=TypeSavTicket.DESTRUCTION,
            statut=StatutSavTicket.DETRUIT,
            quantite=2,
            created_by=magasinier,
        )

        assert get_real_available_stock(part.pk) == 8

    @pytest.mark.django_db
    def test_un_manquant_sort_du_stock(self, ligne, part):
        ligne.quantite_manquante = 4
        ligne.save(update_fields=["quantite_manquante"])

        assert get_unavailable_stock_quantity(part.pk) == 4
        assert get_real_available_stock(part.pk) == 6

    @pytest.mark.django_db
    def test_le_stock_reel_ne_descend_pas_sous_zero(self, ligne, part):
        ligne.quantite_manquante = 99
        ligne.save(update_fields=["quantite_manquante"])

        assert get_real_available_stock(part.pk) == 0

    @pytest.mark.django_db
    def test_part_sans_extension_louable(self, db):
        orpheline = Part.objects.create(name="Hors catalogue")

        assert get_real_available_stock(orpheline.pk) == 0


class TestSaisieRetour:
    @pytest.mark.django_db
    def test_ventilation_complete(self, factory, magasinier, reservation, ligne):
        response = _patch_retour(
            factory,
            magasinier,
            reservation,
            {
                "commentaire": "Retour terrain",
                "lignes": [
                    {
                        "ligne": ligne.pk,
                        "quantite_ramassee": 3,
                        "quantite_sav": 1,
                        "quantite_detruite": 1,
                        "quantite_manquante": 1,
                        "facturer_client": True,
                        "commentaire": "Une toile déchirée",
                    }
                ],
            },
        )

        assert response.status_code == status.HTTP_200_OK

        ligne.refresh_from_db()
        reservation.refresh_from_db()

        assert ligne.quantite_ramassee == 3
        assert ligne.quantite_sav == 1
        assert ligne.quantite_detruite == 1
        assert ligne.quantite_manquante == 1
        assert ligne.quantite_retournee == 3
        # Quatre natures de retour sur la même ligne : l'état est « mixte ».
        assert ligne.etat_retour == "mixte"
        assert reservation.statut == StatutReservation.RETOURNEE
        assert reservation.date_retour_reelle is not None
        assert reservation.commentaire == "Retour terrain"

        assert len(response.data["sav_tickets"]) == 2
        assert SavTicket.objects.filter(
            type_ticket=TypeSavTicket.REPARATION, statut=StatutSavTicket.OUVERT
        ).count() == 1
        assert SavTicket.objects.filter(
            type_ticket=TypeSavTicket.DESTRUCTION, statut=StatutSavTicket.DETRUIT
        ).count() == 1

    @pytest.mark.django_db
    def test_retour_complet_sans_incident(self, factory, magasinier, reservation, ligne):
        response = _patch_retour(
            factory,
            magasinier,
            reservation,
            {"lignes": [{"ligne": ligne.pk, "quantite_ramassee": 6}]},
        )

        ligne.refresh_from_db()

        assert response.status_code == status.HTTP_200_OK
        assert ligne.etat_retour == "ok"
        assert SavTicket.objects.count() == 0
        assert response.data["sav_tickets"] == []

    @pytest.mark.django_db
    def test_le_stock_reel_baisse_apres_la_saisie(
        self, factory, magasinier, reservation, ligne, part
    ):
        assert get_real_available_stock(part.pk) == 10

        _patch_retour(
            factory,
            magasinier,
            reservation,
            {
                "lignes": [
                    {
                        "ligne": ligne.pk,
                        "quantite_ramassee": 3,
                        "quantite_sav": 2,
                        "quantite_detruite": 1,
                    }
                ]
            },
        )

        # 2 en réparation + 1 détruit sortent des 10 exemplaires.
        assert get_real_available_stock(part.pk) == 7

    @pytest.mark.django_db
    def test_remettre_une_quantite_a_zero_cloture_le_ticket(
        self, factory, magasinier, reservation, ligne
    ):
        _patch_retour(
            factory,
            magasinier,
            reservation,
            {"lignes": [{"ligne": ligne.pk, "quantite_sav": 2}]},
        )

        ticket = SavTicket.objects.get(type_ticket=TypeSavTicket.REPARATION)

        assert ticket.statut == StatutSavTicket.OUVERT

        # Correction de saisie : plus rien au SAV.
        _patch_retour(
            factory,
            magasinier,
            reservation,
            {"lignes": [{"ligne": ligne.pk, "quantite_ramassee": 6}]},
        )

        ticket.refresh_from_db()

        assert ticket.statut == StatutSavTicket.CLOTURE
        assert ticket.quantite == 0
        assert ticket.closed_at is not None

    @pytest.mark.django_db
    def test_somme_superieure_a_la_quantite_livree_refusee(
        self, factory, magasinier, reservation, ligne
    ):
        response = _patch_retour(
            factory,
            magasinier,
            reservation,
            {
                "lignes": [
                    {
                        "ligne": ligne.pk,
                        "quantite_ramassee": 6,
                        "quantite_manquante": 1,
                    }
                ]
            },
        )

        ligne.refresh_from_db()

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert ligne.quantite_ramassee == 0

    @pytest.mark.django_db
    def test_ligne_dune_autre_reservation_refusee(
        self, factory, magasinier, reservation, ligne, part
    ):
        autre = Reservation.objects.create(
            prestation=reservation.prestation,
            demandeur=magasinier,
            date_demande=timezone.now(),
            statut=StatutReservation.LIVREE,
        )
        ligne_autre = LigneReservation.objects.create(
            reservation=autre,
            part=part,
            quantite_demandee=2,
            quantite_livree=2,
        )

        response = _patch_retour(
            factory,
            magasinier,
            reservation,
            {"lignes": [{"ligne": ligne_autre.pk, "quantite_ramassee": 1}]},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_ligne_inconnue_refusee(self, factory, magasinier, reservation):
        response = _patch_retour(
            factory,
            magasinier,
            reservation,
            {"lignes": [{"ligne": 999999, "quantite_ramassee": 1}]},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_reservation_inconnue_renvoie_404(self, factory, magasinier, db):
        request = factory.patch(
            RETOUR_URL.format(pk=999999), {"lignes": []}, format="json"
        )
        force_authenticate(request, user=magasinier)

        response = RamassageRetourView.as_view()(request, pk=999999)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_un_statut_non_livree_nest_pas_ecrase(
        self, factory, magasinier, reservation, ligne
    ):
        reservation.statut = StatutReservation.CLOTUREE
        reservation.save(update_fields=["statut"])

        _patch_retour(
            factory,
            magasinier,
            reservation,
            {"lignes": [{"ligne": ligne.pk, "quantite_ramassee": 6}]},
        )

        reservation.refresh_from_db()

        assert reservation.statut == StatutReservation.CLOTUREE


class TestSaisieRetourRoles:
    """La saisie suit la règle du bloc retours : magasinier ou admin."""

    @pytest.mark.django_db
    def test_gestionnaire_refuse(self, factory, gestionnaire, reservation, ligne):
        response = _patch_retour(
            factory,
            gestionnaire,
            reservation,
            {"lignes": [{"ligne": ligne.pk, "quantite_ramassee": 6}]},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_magasinier_autorise(self, factory, magasinier, reservation, ligne):
        response = _patch_retour(
            factory,
            magasinier,
            reservation,
            {"lignes": [{"ligne": ligne.pk, "quantite_ramassee": 6}]},
        )

        assert response.status_code == status.HTTP_200_OK


class TestTicketsSav:
    @pytest.fixture
    def ticket(self, db, ligne, part, magasinier):
        return SavTicket.objects.create(
            ligne_reservation=ligne,
            reservation=ligne.reservation,
            part=part,
            type_ticket=TypeSavTicket.REPARATION,
            statut=StatutSavTicket.OUVERT,
            quantite=2,
            created_by=magasinier,
        )

    @pytest.mark.django_db
    def test_liste_visible_par_les_roles_plugin(self, factory, gestionnaire, ticket):
        request = factory.get(TICKETS_URL)
        force_authenticate(request, user=gestionnaire)

        response = SavTicketListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1

    @pytest.mark.django_db
    def test_le_role_sav_peut_faire_avancer_un_ticket(
        self, factory, technicien_sav, ticket
    ):
        """Sans `SavPermission`, l'écriture n'était ouverte qu'à l'admin."""

        request = factory.patch(
            f"{TICKETS_URL}{ticket.pk}/",
            {"statut": StatutSavTicket.EN_REPARATION, "diagnostic": "Couture"},
            format="json",
        )
        force_authenticate(request, user=technicien_sav)

        response = SavTicketDetailView.as_view()(request, pk=ticket.pk)

        ticket.refresh_from_db()

        assert response.status_code == status.HTTP_200_OK
        assert ticket.statut == StatutSavTicket.EN_REPARATION

    @pytest.mark.django_db
    def test_le_gestionnaire_ne_modifie_pas_un_ticket(
        self, factory, gestionnaire, ticket
    ):
        request = factory.patch(
            f"{TICKETS_URL}{ticket.pk}/",
            {"statut": StatutSavTicket.REPARE},
            format="json",
        )
        force_authenticate(request, user=gestionnaire)

        response = SavTicketDetailView.as_view()(request, pk=ticket.pk)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_liste_des_detruits(self, factory, technicien_sav, ligne, part, magasinier):
        SavTicket.objects.create(
            ligne_reservation=ligne,
            reservation=ligne.reservation,
            part=part,
            type_ticket=TypeSavTicket.DESTRUCTION,
            statut=StatutSavTicket.DETRUIT,
            quantite=1,
            created_by=magasinier,
        )
        SavTicket.objects.create(
            ligne_reservation=ligne,
            reservation=ligne.reservation,
            part=part,
            type_ticket=TypeSavTicket.REPARATION,
            statut=StatutSavTicket.OUVERT,
            quantite=1,
            created_by=magasinier,
        )

        request = factory.get(DETRUITS_URL)
        force_authenticate(request, user=technicien_sav)

        response = DestroyedItemsListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        # Seuls les tickets de destruction, pas les réparations en cours.
        assert response.data["count"] == 1
