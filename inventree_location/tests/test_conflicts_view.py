from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from django.contrib.auth import get_user_model

from inventree_location.models import Reservation
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
    from inventree_location.models import Prestation, Manifestation, Groupe, RentableItem

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
    def test_returns_conflicting_reservations_sorted_by_start(self, factory, user, setup_conflicts):
        request = factory.get("/plugin/inventree-location/conflicts/")
        force_authenticate(request, user=user)

        response = ConflictsListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["id"] == setup_conflicts["first"].pk
        assert response.data[0]["conflict_count"] == 1
