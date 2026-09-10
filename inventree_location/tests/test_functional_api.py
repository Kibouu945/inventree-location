"""Tests fonctionnels de bout en bout.

Contrairement aux tests de vues (qui instancient les vues via
APIRequestFactory), ceux-ci passent par le routeur d'URLs réel
(`tests.functional_urls`) et par l'authentification par token, comme en
production : URL -> TokenAuthentication -> permission de rôle -> vue ->
serializer -> base SQLite.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from inventree_location import roles
from inventree_location.models import (
    Prestation,
    Reservation,
)
from inventree_location.tests.factories import make_manifestation
from part.models import Part, PartCategory

User = get_user_model()

BASE = "/plugin/inventree-location"

pytestmark = [pytest.mark.django_db, pytest.mark.urls("tests.functional_urls")]


def client_for(role=None, *, superuser=False, username="u"):
    """Retourne un APIClient authentifié par token pour un user au rôle donné."""

    if superuser:
        user = User.objects.create_superuser(username=username, password="pwd12345")
    else:
        user = User.objects.create_user(username=username, password="pwd12345")
        if role is not None:
            user.groups.add(Group.objects.get(name=role))

    token = Token.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client, user


@pytest.fixture
def prestation():
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
# Authentification
# ---------------------------------------------------------------------------


def test_anonymous_is_rejected():
    client = APIClient()
    response = client.get(f"{BASE}/catalog/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_token_without_role_is_forbidden():
    client, _ = client_for(role=None, username="norole")
    response = client.get(f"{BASE}/catalog/")
    assert response.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Catalogue — lecture, filtres, écriture par rôle
# ---------------------------------------------------------------------------


def test_catalog_read_and_filter_end_to_end():
    cat = PartCategory.objects.create(name="Tentes")
    Part.objects.create(name="Tente 4 places", category=cat)
    Part.objects.create(name="Réchaud gaz", category=cat)

    client, _ = client_for(roles.LECTEUR, username="lecteur")

    response = client.get(f"{BASE}/catalog/", {"search": "tente"})
    assert response.status_code == status.HTTP_200_OK
    names = {row["name"] for row in response.data["results"]}
    assert names == {"Tente 4 places"}


def test_lecteur_cannot_bulk_update_catalog():
    Part.objects.create(name="Tente")
    client, _ = client_for(roles.LECTEUR, username="lecteur")

    response = client.patch(
        f"{BASE}/catalog/rentable/",
        {"part_ids": [1], "is_rentable": False},
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_rentable_detail_roundtrip():
    part = Part.objects.create(name="Tente")
    client, _ = client_for(roles.GESTIONNAIRE, username="gest")

    # Défauts quand aucun RentableItem n'existe.
    get_default = client.get(f"{BASE}/catalog/{part.pk}/rentable/")
    assert get_default.status_code == status.HTTP_200_OK
    assert get_default.data["is_rentable"] is True

    # Mise à jour.
    patched = client.patch(
        f"{BASE}/catalog/{part.pk}/rentable/",
        {"is_rentable": False, "consommable": True},
        format="json",
    )
    assert patched.status_code == status.HTTP_200_OK

    # Relecture reflète l'état persisté.
    get_after = client.get(f"{BASE}/catalog/{part.pk}/rentable/")
    assert get_after.data["is_rentable"] is False
    assert get_after.data["consommable"] is True


# ---------------------------------------------------------------------------
# Réservations — création avec lignes, filtres, écriture par rôle
# ---------------------------------------------------------------------------


def test_create_reservation_with_nested_lignes(prestation):
    part = Part.objects.create(name="Tente")
    client, user = client_for(roles.GESTIONNAIRE, username="gest")

    payload = {
        "prestation": prestation.pk,
        "demandeur": user.pk,
        "date_demande": timezone.now().isoformat(),
        "lignes": [{"part": part.pk, "quantite_demandee": 3}],
    }
    response = client.post(f"{BASE}/reservations/", payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    reservation = Reservation.objects.get()
    assert reservation.lignes.get().quantite_demandee == 3


def test_reservation_list_filter_by_statut(prestation):
    client, user = client_for(roles.GESTIONNAIRE, username="gest")
    Reservation.objects.create(
        prestation=prestation,
        demandeur=user,
        date_demande=timezone.now(),
        statut="brouillon",
    )
    validee = Reservation.objects.create(
        prestation=prestation,
        demandeur=user,
        date_demande=timezone.now(),
        statut="validee",
    )

    response = client.get(f"{BASE}/reservations/", {"statut": "validee"})
    assert response.status_code == status.HTTP_200_OK
    assert [row["id"] for row in response.data["results"]] == [validee.pk]


def test_livreur_only_sees_validated_reservations(prestation):
    # Un livreur pur ne voit que les réservations validées.
    gestionnaire = User.objects.create_user(username="gest2", password="pwd12345")
    for statut in ("brouillon", "soumise", "livree", "cloturee"):
        Reservation.objects.create(
            prestation=prestation,
            demandeur=gestionnaire,
            date_demande=timezone.now(),
            statut=statut,
        )
    validee = Reservation.objects.create(
        prestation=prestation,
        demandeur=gestionnaire,
        date_demande=timezone.now(),
        statut="validee",
    )

    client, _ = client_for(roles.LIVREUR, username="livreur_view")
    response = client.get(f"{BASE}/reservations/")

    assert response.status_code == status.HTTP_200_OK
    assert [row["id"] for row in response.data["results"]] == [validee.pk]


def test_gestionnaire_sees_all_reservation_statuses(prestation):
    # Contre-exemple : un rôle de gestion garde la visibilité totale.
    client, user = client_for(roles.GESTIONNAIRE, username="gest3")
    for statut in ("brouillon", "soumise", "validee", "livree"):
        Reservation.objects.create(
            prestation=prestation,
            demandeur=user,
            date_demande=timezone.now(),
            statut=statut,
        )

    response = client.get(f"{BASE}/reservations/")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 4


def test_magasinier_cannot_create_reservation(prestation):
    client, user = client_for(roles.MAGASINIER, username="mag")
    payload = {
        "prestation": prestation.pk,
        "demandeur": user.pk,
        "date_demande": timezone.now().isoformat(),
    }
    response = client.post(f"{BASE}/reservations/", payload, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_superuser_can_write_without_role(prestation):
    client, user = client_for(superuser=True, username="root")
    payload = {
        "prestation": prestation.pk,
        "demandeur": user.pk,
        "date_demande": timezone.now().isoformat(),
    }
    response = client.post(f"{BASE}/reservations/", payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED


def test_validated_reservation_not_editable(prestation):
    client, user = client_for(roles.GESTIONNAIRE, username="gest_edit")
    reservation = Reservation.objects.create(
        prestation=prestation,
        demandeur=user,
        date_demande=timezone.now(),
        statut="validee",
    )
    response = client.patch(
        f"{BASE}/reservations/{reservation.pk}/",
        {"commentaire": "modif"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "detail" in response.data


def test_only_brouillon_is_deletable(prestation):
    client, user = client_for(roles.GESTIONNAIRE, username="gest_del")

    validee = Reservation.objects.create(
        prestation=prestation,
        demandeur=user,
        date_demande=timezone.now(),
        statut="validee",
    )
    response = client.delete(f"{BASE}/reservations/{validee.pk}/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert Reservation.objects.filter(pk=validee.pk).exists()

    brouillon = Reservation.objects.create(
        prestation=prestation,
        demandeur=user,
        date_demande=timezone.now(),
        statut="brouillon",
    )
    response = client.delete(f"{BASE}/reservations/{brouillon.pk}/")
    assert response.status_code == status.HTTP_204_NO_CONTENT
