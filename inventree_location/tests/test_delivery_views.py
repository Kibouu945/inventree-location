from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from inventree_location import roles
from inventree_location.models import (
    Groupe,
    Lieu,
    Manifestation,
    Prestation,
    Profile,
    Reservation,
)
from inventree_location.views import DeliveryListView

from part.models import Part, PartCategory

User = get_user_model()


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def gestionnaire(db):
    group, _created = Group.objects.get_or_create(name=roles.GESTIONNAIRE)
    account = User.objects.create_user(username="gest", password="pwd12345")
    account.groups.add(group)
    return account


@pytest.fixture
def livreur(db):
    group, _created = Group.objects.get_or_create(name=roles.LIVREUR)
    account = User.objects.create_user(username="livreur1", password="pwd12345")
    account.groups.add(group)
    return account


@pytest.fixture
def organisateur(db):
    return User.objects.create_user(
        username="org", password="pwd12345", first_name="Ora", last_name="Nisatrice"
    )


@pytest.fixture
def lieu(db):
    return Lieu.objects.create(
        nom="Chalet", adresse="1 rue du Camp", latitude="45.1", longitude="5.7"
    )


@pytest.fixture
def part(db):
    category = PartCategory.objects.create(name="Catégorie")
    return Part.objects.create(name="Tente", category=category)


@pytest.fixture
def manifestation(db, organisateur):
    groupe = Groupe.objects.create(nom="Groupe A", code="GA")
    return Manifestation.objects.create(
        nom="Camp",
        date_debut="2026-06-01T00:00:00Z",
        date_fin="2026-06-05T00:00:00Z",
        statut="planifiee",
        organisateur=organisateur,
        groupe=groupe,
    )


@pytest.fixture
def prestation(db, manifestation, lieu):
    return Prestation.objects.create(
        manifestation=manifestation,
        nom="Prestation",
        lieu=lieu,
        date_debut="2026-06-01T00:00:00Z",
        date_fin="2026-06-05T00:00:00Z",
    )


def _make_reservation(prestation, part, *, statut, date_retrait, date_retour, quantite=1):
    reservation = Reservation.objects.create(
        prestation=prestation,
        demandeur=User.objects.create_user(
            username=f"demandeur-{Reservation.objects.count()}", password="pwd"
        ),
        statut=statut,
        date_retrait_prevue=date_retrait,
        date_retour_prevue=date_retour,
    )
    reservation.lignes.create(part=part, quantite_demandee=quantite)
    return reservation


class TestDeliveryListView:
    def test_anonymous_returns_401(self, factory, prestation, part):
        _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )

        request = factory.get("/plugin/inventree-location/deliveries/")
        response = DeliveryListView.as_view()(request)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_pure_livreur_only_sees_validee_regardless_of_statut_param(
        self, factory, livreur, prestation, part
    ):
        to_deliver = _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )
        _make_reservation(
            prestation,
            part,
            statut="livree",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )

        # Un livreur pur reste forcé sur "validee" même s'il demande "livree".
        request = factory.get(
            "/plugin/inventree-location/deliveries/", {"statut": "livree"}
        )
        force_authenticate(request, user=livreur)
        response = DeliveryListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        ids = [row["id"] for row in response.data]
        assert ids == [to_deliver.pk]

    @pytest.mark.django_db
    def test_default_statut_scope_is_validee_and_livree(
        self, factory, gestionnaire, prestation, part
    ):
        validee = _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )
        livree = _make_reservation(
            prestation,
            part,
            statut="livree",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )
        _make_reservation(
            prestation,
            part,
            statut="refusee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )

        request = factory.get("/plugin/inventree-location/deliveries/")
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        ids = {row["id"] for row in response.data}
        assert ids == {validee.pk, livree.pk}

    @pytest.mark.django_db
    def test_date_filter(self, factory, gestionnaire, prestation, part):
        in_range = _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )
        _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-07-10T00:00:00Z",
            date_retour="2026-07-11T00:00:00Z",
        )

        request = factory.get(
            "/plugin/inventree-location/deliveries/",
            {"date_from": "2026-06-01", "date_to": "2026-06-30"},
        )
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        ids = [row["id"] for row in response.data]
        assert ids == [in_range.pk]

    @pytest.mark.django_db
    def test_lieu_filter(self, factory, gestionnaire, manifestation, part, lieu):
        other_lieu = Lieu.objects.create(nom="Gymnase", adresse="2 rue du Sport")
        other_prestation = Prestation.objects.create(
            manifestation=manifestation,
            nom="Autre prestation",
            lieu=other_lieu,
            date_debut="2026-06-01T00:00:00Z",
            date_fin="2026-06-05T00:00:00Z",
        )
        prestation_at_lieu = Prestation.objects.create(
            manifestation=manifestation,
            nom="Prestation",
            lieu=lieu,
            date_debut="2026-06-01T00:00:00Z",
            date_fin="2026-06-05T00:00:00Z",
        )

        wanted = _make_reservation(
            prestation_at_lieu,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )
        _make_reservation(
            other_prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )

        request = factory.get(
            "/plugin/inventree-location/deliveries/", {"lieu": str(lieu.pk)}
        )
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        ids = [row["id"] for row in response.data]
        assert ids == [wanted.pk]

    @pytest.mark.django_db
    def test_organisateur_contact_populated_when_profile_exists(
        self, factory, gestionnaire, prestation, part, organisateur
    ):
        Profile.objects.create(user=organisateur, telephone="0102030405")
        reservation = _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )

        request = factory.get("/plugin/inventree-location/deliveries/")
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        row = next(r for r in response.data if r["id"] == reservation.pk)
        assert row["organisateur_telephone"] == "0102030405"
        assert "Nisatrice" in row["organisateur_nom"]

    @pytest.mark.django_db
    def test_organisateur_telephone_empty_without_profile(
        self, factory, gestionnaire, prestation, part
    ):
        # Aucun Profile pour l'organisateur : ne doit pas lever de 500.
        reservation = _make_reservation(
            prestation,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )

        request = factory.get("/plugin/inventree-location/deliveries/")
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        row = next(r for r in response.data if r["id"] == reservation.pk)
        assert row["organisateur_telephone"] == ""

    @pytest.mark.django_db
    def test_quantite_totale_sums_lignes(
        self, factory, gestionnaire, prestation, part
    ):
        reservation = Reservation.objects.create(
            prestation=prestation,
            demandeur=User.objects.create_user(username="dem", password="pwd"),
            statut="validee",
            date_retrait_prevue="2026-06-02T00:00:00Z",
            date_retour_prevue="2026-06-03T00:00:00Z",
        )
        reservation.lignes.create(part=part, quantite_demandee=3)
        other_category = PartCategory.objects.create(name="Autre")
        other_part = Part.objects.create(name="Piquet", category=other_category)
        reservation.lignes.create(part=other_part, quantite_demandee=5)

        request = factory.get("/plugin/inventree-location/deliveries/")
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        row = next(r for r in response.data if r["id"] == reservation.pk)
        assert row["quantite_totale"] == 8

    @pytest.mark.django_db
    def test_lieu_detail_null_when_prestation_has_no_lieu(
        self, factory, gestionnaire, manifestation, part
    ):
        prestation_sans_lieu = Prestation.objects.create(
            manifestation=manifestation,
            nom="Prestation sans lieu",
            date_debut="2026-06-01T00:00:00Z",
            date_fin="2026-06-05T00:00:00Z",
        )
        reservation = _make_reservation(
            prestation_sans_lieu,
            part,
            statut="validee",
            date_retrait="2026-06-02T00:00:00Z",
            date_retour="2026-06-03T00:00:00Z",
        )

        request = factory.get("/plugin/inventree-location/deliveries/")
        force_authenticate(request, user=gestionnaire)
        response = DeliveryListView.as_view()(request)

        row = next(r for r in response.data if r["id"] == reservation.pk)
        assert row["lieu_detail"] is None
