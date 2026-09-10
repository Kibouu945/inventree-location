"""TR-03 : tests des 7 rôles et de leurs accès autorisés / bloqués.

Un utilisateur par rôle vérifie, sur chaque endpoint sensible, que la lecture
et l'écriture sont autorisées ou refusées conformément au mapping des
permissions (cf. permissions.py).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location import roles
from inventree_location.models import Prestation, Reservation
from inventree_location.views import (
    CatalogPartListView,
    LieuListCreateView,
    RentableFlagBulkUpdateView,
    ReservationListCreateView,
)
from inventree_location.tests.factories import make_manifestation

User = get_user_model()

CATALOG_URL = "/plugin/inventree-location/catalog/"
BULK_URL = "/plugin/inventree-location/catalog/rentable/"
RESA_URL = "/plugin/inventree-location/reservations/"
LIEUX_URL = "/plugin/inventree-location/lieux/"


@pytest.fixture
def factory():
    return APIRequestFactory()


def make_user(username, role=None):
    account = User.objects.create_user(username=username, password="pwd12345")
    if role is not None:
        account.groups.add(Group.objects.get(name=role))
    return account


@pytest.fixture
def prestation(db):
    now = timezone.now()
    manifestation = make_manifestation(
        nom="Camp",
        date_debut=now,
        date_fin=now + timedelta(days=7),
    )
    return Prestation.objects.create(
        manifestation=manifestation,
        nom="Installation",
        date_debut=now,
        date_fin=now + timedelta(hours=4),
    )


# ---------------------------------------------------------------------------
# Création des groupes (migration TR-03)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_all_role_groups_exist():
    existing = set(Group.objects.values_list("name", flat=True))
    assert set(roles.ALL_ROLES).issubset(existing)


# ---------------------------------------------------------------------------
# Lecture : tous les rôles peuvent lire le catalogue
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("role", roles.ALL_ROLES)
def test_every_role_can_read_catalog(factory, role):
    user = make_user(f"reader-{role}", role)
    request = factory.get(CATALOG_URL)
    force_authenticate(request, user=user)

    response = CatalogPartListView.as_view()(request)
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_user_without_role_is_denied(factory):
    user = make_user("sans-role")
    request = factory.get(CATALOG_URL)
    force_authenticate(request, user=user)

    response = CatalogPartListView.as_view()(request)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_superuser_is_allowed_without_role(factory):
    user = User.objects.create_superuser(username="root", password="pwd12345")
    request = factory.get(CATALOG_URL)
    force_authenticate(request, user=user)

    response = CatalogPartListView.as_view()(request)
    assert response.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# Écriture réservation : admin / gestionnaire / organisateur autorisés
# ---------------------------------------------------------------------------


WRITE_RESA_ALLOWED = {roles.ADMIN, roles.GESTIONNAIRE, roles.ORGANISATEUR}


@pytest.mark.django_db
@pytest.mark.parametrize("role", roles.ALL_ROLES)
def test_reservation_write_respects_role(factory, prestation, role):
    user = make_user(f"writer-{role}", role)
    payload = {
        "prestation": prestation.pk,
        "demandeur": user.pk,
        "date_demande": timezone.now().isoformat(),
    }
    request = factory.post(RESA_URL, payload)
    force_authenticate(request, user=user)

    response = ReservationListCreateView.as_view()(request)

    if role in WRITE_RESA_ALLOWED:
        assert response.status_code == status.HTTP_201_CREATED
        assert Reservation.objects.count() == 1
    else:
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert Reservation.objects.count() == 0


# ---------------------------------------------------------------------------
# Écriture catalogue (bulk-update louable) : admin / gestionnaire autorisés
# ---------------------------------------------------------------------------


WRITE_CATALOG_ALLOWED = {roles.ADMIN, roles.GESTIONNAIRE}


@pytest.mark.django_db
@pytest.mark.parametrize("role", roles.ALL_ROLES)
def test_catalog_bulk_update_respects_role(factory, role):
    user = make_user(f"flagger-{role}", role)
    request = factory.patch(
        BULK_URL, {"part_ids": [1], "is_rentable": False}, format="json"
    )
    force_authenticate(request, user=user)

    response = RentableFlagBulkUpdateView.as_view()(request)

    if role in WRITE_CATALOG_ALLOWED:
        # 200 : la liste de parts est vide en test mais l'accès est autorisé.
        assert response.status_code == status.HTTP_200_OK
    else:
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Écriture lieu : admin / gestionnaire autorisés
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("role", [roles.MAGASINIER, roles.LECTEUR, roles.LIVREUR])
def test_lieu_write_denied_for_non_managers(factory, prestation, role):
    user = make_user(f"lieu-{role}", role)
    payload = {"prestation": prestation.pk, "nom": "Salle A"}
    request = factory.post(LIEUX_URL, payload)
    force_authenticate(request, user=user)

    response = LieuListCreateView.as_view()(request)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
@pytest.mark.parametrize("role", [roles.ADMIN, roles.GESTIONNAIRE])
def test_lieu_write_allowed_for_managers(factory, prestation, role):
    user = make_user(f"lieu-{role}", role)
    payload = {"prestation": prestation.pk, "nom": "Salle A"}
    request = factory.post(LIEUX_URL, payload)
    force_authenticate(request, user=user)

    response = LieuListCreateView.as_view()(request)
    assert response.status_code == status.HTTP_201_CREATED


# ---------------------------------------------------------------------------
# Helpers de roles.py
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_user_roles_helper():
    user = make_user("multi", roles.GESTIONNAIRE)
    assert roles.user_roles(user) == {roles.GESTIONNAIRE}
    assert roles.user_has_any_role(user, [roles.ADMIN, roles.GESTIONNAIRE]) is True
    assert roles.user_has_any_role(user, [roles.LECTEUR]) is False


@pytest.mark.django_db
def test_sees_only_deliverable_reservations_pure_livreur():
    user = make_user("livreur-pur", roles.LIVREUR)
    assert roles.sees_only_deliverable_reservations(user) is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role",
    [roles.ADMIN, roles.GESTIONNAIRE, roles.ORGANISATEUR, roles.MAGASINIER, roles.SAV],
)
def test_sees_only_deliverable_reservations_false_for_managers(role):
    user = make_user(f"full-{role}", role)
    assert roles.sees_only_deliverable_reservations(user) is False


@pytest.mark.django_db
def test_sees_only_deliverable_reservations_livreur_with_broader_role():
    # Un livreur qui cumule un rôle à visibilité complète n'est pas restreint.
    user = make_user("livreur-gest", roles.LIVREUR)
    user.groups.add(Group.objects.get(name=roles.GESTIONNAIRE))
    assert roles.sees_only_deliverable_reservations(user) is False


@pytest.mark.django_db
def test_sees_only_deliverable_reservations_false_for_superuser():
    root = User.objects.create_superuser(username="root-livreur", password="pwd12345")
    root.groups.add(Group.objects.get(name=roles.LIVREUR))
    assert roles.sees_only_deliverable_reservations(root) is False
