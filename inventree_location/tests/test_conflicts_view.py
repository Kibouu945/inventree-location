from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from django.contrib.auth import get_user_model

from inventree_location.models import Reservation
from inventree_location.tests.factories import fixer_stock, mettre_en_stock
from inventree_location.views import ConflictsListView

from part.models import Part, PartCategory

User = get_user_model()


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def user(db):
    from django.contrib.auth.models import Group

    from inventree_location import roles

    group, _created = Group.objects.get_or_create(name=roles.GESTIONNAIRE)
    account = User.objects.create_user(username="alice", password="pwd12345")
    account.groups.add(group)
    return account


@pytest.fixture
def setup_conflicts(db):
    """Stock 0 et deux réservations d'1 : pénurie réelle (CON-01)."""

    from inventree_location.models import (
        Prestation,
        Manifestation,
        Groupe,
        RentableItem,
    )

    groupe = Groupe.objects.create(nom="Groupe A", code="GA")
    manifestation = Manifestation.objects.create(
        nom="Camp",
        date_debut="2026-06-01T00:00:00Z",
        date_fin="2026-06-05T00:00:00Z",
        statut="planifiee",
        organisateur=User.objects.create_user(username="org", password="pwd"),
        groupe=groupe,
    )
    prestation = Prestation.objects.create(
        manifestation=manifestation,
        nom="Prestation",
        date_debut="2026-06-01T00:00:00Z",
        date_fin="2026-06-05T00:00:00Z",
    )
    category = PartCategory.objects.create(name="Catégorie")
    part = Part.objects.create(name="Part 1", category=category)
    RentableItem.objects.create(part=part, is_rentable=True)
    first = Reservation.objects.create(
        prestation=prestation,
        demandeur=User.objects.create_user(username="u1", password="pwd"),
        statut="confirmée",
        date_retrait_prevue="2026-06-02T00:00:00Z",
        date_retour_prevue="2026-06-03T00:00:00Z",
    )
    first.lignes.create(part=part, quantite_demandee=1)
    second = Reservation.objects.create(
        prestation=prestation,
        demandeur=User.objects.create_user(username="u2", password="pwd"),
        statut="confirmée",
        date_retrait_prevue="2026-06-02T12:00:00Z",
        date_retour_prevue="2026-06-04T00:00:00Z",
    )
    second.lignes.create(part=part, quantite_demandee=1)
    return {"first": first, "second": second}


class TestConflictsListView:
    def test_anonymous_returns_401(self, factory, setup_conflicts):
        request = factory.get("/plugin/inventree-location/conflicts/")
        response = ConflictsListView.as_view()(request)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_returns_conflicting_reservations_sorted_by_start(
        self, factory, user, setup_conflicts
    ):
        request = factory.get("/plugin/inventree-location/conflicts/")
        force_authenticate(request, user=user)

        response = ConflictsListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["id"] == setup_conflicts["first"].pk
        assert response.data[0]["conflict_count"] == 1

    @pytest.mark.django_db
    def test_overlap_without_shortage_is_not_a_conflict(
        self, factory, user, setup_conflicts
    ):
        """CON-01 : le conflit se mesure aux quantités, pas au chevauchement.

        Les deux réservations chevauchantes demandent 1 chacune ; avec 10 en
        stock elles cohabitent sans se gêner.
        """

        from inventree_location.models import RentableItem

        part_id = setup_conflicts["first"].lignes.first().part_id
        fixer_stock(Part.objects.get(pk=part_id), 10)

        request = factory.get("/plugin/inventree-location/conflicts/")
        force_authenticate(request, user=user)

        response = ConflictsListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    @pytest.mark.django_db
    def test_shortage_details_the_missing_article(
        self, factory, user, setup_conflicts
    ):
        """Le groupe dit quel article manque et de combien."""

        from inventree_location.models import RentableItem

        part_id = setup_conflicts["first"].lignes.first().part_id
        fixer_stock(Part.objects.get(pk=part_id), 1)

        request = factory.get("/plugin/inventree-location/conflicts/")
        force_authenticate(request, user=user)

        response = ConflictsListView.as_view()(request)

        # Stock 1, chacune en demande 1 : il en manque 1.
        assert len(response.data) == 1
        assert response.data[0]["shortages"] == [
            {"part_id": part_id, "part_name": "Part 1", "missing_quantity": 1}
        ]

    @pytest.mark.django_db
    def test_prestation_forecast_alone_raises_a_conflict(
        self, factory, user, setup_conflicts
    ):
        """Une pénurie peut venir du prévisionnel, sans réservation en face."""

        from inventree_location.models import (
            LignePrestation,
            RentableItem,
            Reservation as Resa,
        )

        first = setup_conflicts["first"]
        part_id = first.lignes.first().part_id
        fixer_stock(Part.objects.get(pk=part_id), 2)

        # Seule `first` subsiste, face à une autre prestation qui prévoit 2.
        Resa.objects.filter(pk=setup_conflicts["second"].pk).delete()

        autre = first.prestation.manifestation.prestations.create(
            nom="Autre prestation",
            date_debut=first.prestation.date_debut,
            date_fin=first.prestation.date_fin,
        )
        LignePrestation.objects.create(prestation=autre, part_id=part_id, quantite=2)

        request = factory.get("/plugin/inventree-location/conflicts/")
        force_authenticate(request, user=user)

        response = ConflictsListView.as_view()(request)

        assert len(response.data) == 1
        assert response.data[0]["id"] == first.pk
        assert response.data[0]["conflict_count"] == 0
        assert response.data[0]["shortages"][0]["missing_quantity"] == 1
