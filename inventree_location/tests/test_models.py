"""Tests des modèles Django du plugin InvenTreeLocation (schéma DB-01 v2 MVP)."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from part.models import Part

from inventree_location.models import (
    Groupe,
    Lieu,
    LigneReservation,
    Manifestation,
    Prestation,
    Profile,
    RentableItem,
    Reservation,
    StatutManifestation,
    StatutReservation,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testeur", password="secret123")


@pytest.fixture
def groupe(db):
    return Groupe.objects.create(nom="Jambville", code="JAM")


@pytest.fixture
def part(db):
    return Part.objects.create(name="Tente 4 places", IPN="ART-001")


@pytest.fixture
def manifestation(user, groupe):
    now = timezone.now()
    return Manifestation.objects.create(
        nom="Camp été 2026",
        date_debut=now,
        date_fin=now + timedelta(days=7),
        organisateur=user,
        groupe=groupe,
    )


@pytest.fixture
def prestation(manifestation):
    return Prestation.objects.create(
        manifestation=manifestation,
        nom="Installation",
        date_debut=manifestation.date_debut,
        date_fin=manifestation.date_debut + timedelta(hours=4),
    )


@pytest.fixture
def reservation(prestation, user):
    return Reservation.objects.create(
        prestation=prestation,
        demandeur=user,
        date_demande=timezone.now(),
    )


@pytest.fixture
def ligne(reservation, part):
    return LigneReservation.objects.create(
        reservation=reservation,
        part=part,
        quantite_demandee=5,
    )


def _get_on_delete(model, field_name):
    return model._meta.get_field(field_name).remote_field.on_delete


# ---------------------------------------------------------------------------
# Groupe
# ---------------------------------------------------------------------------


class TestGroupe:
    def test_creation(self, groupe):
        assert groupe.pk is not None
        assert groupe.nom == "Jambville"
        assert groupe.code == "JAM"

    def test_str(self, groupe):
        assert str(groupe) == "Jambville"

    @pytest.mark.django_db
    def test_nom_unique(self, groupe):
        with pytest.raises(IntegrityError), transaction.atomic():
            Groupe.objects.create(nom="Jambville", code="OTHER")

    @pytest.mark.django_db
    def test_code_unique(self, groupe):
        with pytest.raises(IntegrityError), transaction.atomic():
            Groupe.objects.create(nom="Autre", code="JAM")


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


class TestProfile:
    @pytest.mark.django_db
    def test_creation(self, user, groupe):
        profile = Profile.objects.create(user=user, groupe=groupe, telephone="0612345678")
        assert profile.pk is not None
        assert profile.groupe == groupe

    @pytest.mark.django_db
    def test_str_with_full_name(self):
        u = User.objects.create_user(username="jdoe", first_name="Jean", last_name="Doe")
        profile = Profile.objects.create(user=u)
        assert str(profile) == "Jean Doe"

    @pytest.mark.django_db
    def test_str_fallback_username(self, user):
        profile = Profile.objects.create(user=user)
        assert str(profile) == "testeur"

    @pytest.mark.django_db
    def test_no_timestamps(self, user):
        profile = Profile.objects.create(user=user)
        assert not hasattr(profile, "created_at")

    def test_on_delete_user_cascade(self):
        assert _get_on_delete(Profile, "user") == models.CASCADE

    def test_on_delete_groupe_protect(self):
        assert _get_on_delete(Profile, "groupe") == models.PROTECT


# ---------------------------------------------------------------------------
# RentableItem
# ---------------------------------------------------------------------------


class TestRentableItem:
    @pytest.mark.django_db
    def test_creation(self, part):
        item = RentableItem.objects.create(
            part=part,
            caution="50.00",
            valeur_remplacement="200.00",
            seuil_alerte_bas=2,
        )
        assert item.pk is not None
        assert item.is_rentable is True
        assert item.consommable is False
        assert item.is_virtual is False
        assert part.rentable_info == item

    @pytest.mark.django_db
    def test_is_virtual_persists(self, part):
        item = RentableItem.objects.create(part=part, is_virtual=True)
        item.refresh_from_db()
        assert item.is_virtual is True

    @pytest.mark.django_db
    def test_one_to_one_unique(self, part):
        RentableItem.objects.create(part=part)
        with pytest.raises(IntegrityError), transaction.atomic():
            RentableItem.objects.create(part=part)

    def test_on_delete_part_cascade(self):
        assert _get_on_delete(RentableItem, "part") == models.CASCADE


# ---------------------------------------------------------------------------
# Manifestation
# ---------------------------------------------------------------------------


class TestManifestation:
    def test_creation(self, manifestation):
        assert manifestation.pk is not None
        assert manifestation.statut == StatutManifestation.BROUILLON

    def test_str(self, manifestation):
        assert str(manifestation) == "Camp été 2026"

    def test_on_delete_organisateur_protect(self):
        assert _get_on_delete(Manifestation, "organisateur") == models.PROTECT

    def test_on_delete_groupe_protect(self):
        assert _get_on_delete(Manifestation, "groupe") == models.PROTECT


# ---------------------------------------------------------------------------
# Prestation
# ---------------------------------------------------------------------------


class TestPrestation:
    def test_creation(self, prestation):
        assert prestation.pk is not None
        assert prestation.nom == "Installation"

    def test_str(self, prestation):
        assert str(prestation) == "Installation"

    def test_on_delete_manifestation_protect(self):
        assert _get_on_delete(Prestation, "manifestation") == models.PROTECT


# ---------------------------------------------------------------------------
# Lieu
# ---------------------------------------------------------------------------


class TestLieu:
    @pytest.mark.django_db
    def test_creation(self, prestation):
        lieu = Lieu.objects.create(
            prestation=prestation,
            nom="Prairie nord",
            latitude="48.987654",
            longitude="1.123456",
            capacite=200,
        )
        assert lieu.pk is not None

    @pytest.mark.django_db
    def test_str(self, prestation):
        lieu = Lieu.objects.create(prestation=prestation, nom="Prairie nord")
        assert str(lieu) == "Prairie nord"

    def test_on_delete_prestation_protect(self):
        assert _get_on_delete(Lieu, "prestation") == models.PROTECT


# ---------------------------------------------------------------------------
# Reservation
# ---------------------------------------------------------------------------


class TestReservation:
    def test_creation(self, reservation):
        assert reservation.pk is not None
        assert reservation.statut == StatutReservation.BROUILLON
        assert reservation.forced is False

    def test_str(self, reservation):
        assert str(reservation) == f"Réservation #{reservation.pk} — Brouillon"

    @pytest.mark.django_db
    def test_forced_persists(self, prestation, user):
        res = Reservation.objects.create(
            prestation=prestation,
            demandeur=user,
            date_demande=timezone.now(),
            forced=True,
        )
        res.refresh_from_db()
        assert res.forced is True

    def test_on_delete_prestation_protect(self):
        assert _get_on_delete(Reservation, "prestation") == models.PROTECT

    def test_on_delete_demandeur_protect(self):
        assert _get_on_delete(Reservation, "demandeur") == models.PROTECT

    def test_on_delete_validateur_protect(self):
        assert _get_on_delete(Reservation, "validateur") == models.PROTECT

    def test_numero_auto_generated(self, reservation):
        year = reservation.date_demande.year
        assert reservation.numero == f"RES-{year}-0001"

    @pytest.mark.django_db
    def test_numero_increments_within_year(self, prestation, user):
        now = timezone.now()
        first = Reservation.objects.create(
            prestation=prestation, demandeur=user, date_demande=now
        )
        second = Reservation.objects.create(
            prestation=prestation, demandeur=user, date_demande=now
        )
        assert first.numero == f"RES-{now.year}-0001"
        assert second.numero == f"RES-{now.year}-0002"

    @pytest.mark.django_db
    def test_numero_not_regenerated_on_update(self, reservation):
        original_numero = reservation.numero
        reservation.commentaire = "mise à jour"
        reservation.save()
        reservation.refresh_from_db()
        assert reservation.numero == original_numero


# ---------------------------------------------------------------------------
# LigneReservation
# ---------------------------------------------------------------------------


class TestLigneReservation:
    def test_creation(self, ligne):
        assert ligne.pk is not None
        assert ligne.quantite_demandee == 5
        assert ligne.quantite_livree == 0
        assert ligne.quantite_retournee == 0
        assert ligne.etat_retour == ""

    def test_str(self, ligne):
        assert str(ligne) == f"part#{ligne.part_id} x5"

    def test_on_delete_reservation_cascade(self):
        assert _get_on_delete(LigneReservation, "reservation") == models.CASCADE

    def test_on_delete_part_protect(self):
        assert _get_on_delete(LigneReservation, "part") == models.PROTECT

    @pytest.mark.django_db
    def test_unique_constraint(self, reservation, part):
        LigneReservation.objects.create(
            reservation=reservation,
            part=part,
            quantite_demandee=3,
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            LigneReservation.objects.create(
                reservation=reservation,
                part=part,
                quantite_demandee=1,
            )


# ---------------------------------------------------------------------------
# TimestampedModel
# ---------------------------------------------------------------------------


class TestTimestamped:
    def test_groupe_has_timestamps(self, groupe):
        assert groupe.created_at is not None
        assert groupe.updated_at is not None

    @pytest.mark.django_db
    def test_updated_at_changes(self, groupe):
        old_updated = groupe.updated_at
        groupe.nom = "Nouveau nom"
        groupe.save()
        groupe.refresh_from_db()
        assert groupe.updated_at > old_updated
