"""Tests des modèles Django du plugin InvenTreeLocation (schéma DB-01 v2 MVP)."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from part.models import Part

from inventree_location.models import (
    Client,
    Contact,
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
def client(db):
    return Client.objects.create(nom="Jambville", email="jambville@exemple.test")


@pytest.fixture
def part(db):
    return Part.objects.create(name="Tente 4 places", IPN="ART-001")


@pytest.fixture
def manifestation(user, client):
    now = timezone.now()
    return Manifestation.objects.create(
        nom="Camp été 2026",
        date_debut=now,
        date_fin=now + timedelta(days=7),
        client=client,
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
# Client et Contact
# ---------------------------------------------------------------------------


class TestClient:
    def test_creation(self, client):
        assert client.pk is not None
        assert client.nom == "Jambville"
        assert client.actif is True

    def test_str(self, client):
        assert str(client) == "Jambville"

    @pytest.mark.django_db
    def test_nom_unique(self, client):
        with pytest.raises(IntegrityError), transaction.atomic():
            Client.objects.create(nom="Jambville", email="autre@exemple.test")

    @pytest.mark.django_db
    def test_email_unique(self, client):
        with pytest.raises(IntegrityError), transaction.atomic():
            Client.objects.create(nom="Autre", email="jambville@exemple.test")

    @pytest.mark.django_db
    def test_plusieurs_clients_sans_email(self, client):
        """L'index unique tolère les NULL : les clients repris n'ont pas d'adresse,"""

        Client.objects.create(nom="Sans adresse 1")
        Client.objects.create(nom="Sans adresse 2")

        assert Client.objects.filter(email=None).count() == 2


class TestContact:
    @pytest.mark.django_db
    def test_creation(self, client):
        contact = Contact.objects.create(
            client=client, nom="Durand", prenom="Paul", telephone="0611223344"
        )

        assert str(contact) == "Paul Durand"
        assert contact.actif is True

    @pytest.mark.django_db
    def test_email_unique_globalement(self, client):
        """Un même interlocuteur ne peut pas avoir deux fiches sous la même"""

        autre = Client.objects.create(nom="Autre client")
        Contact.objects.create(client=client, nom="Durand", email="p@exemple.test")

        with pytest.raises(IntegrityError), transaction.atomic():
            Contact.objects.create(client=autre, nom="Durand", email="p@exemple.test")

    def test_on_delete_client_cascade(self):
        assert _get_on_delete(Contact, "client") == models.CASCADE


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


class TestProfile:
    @pytest.mark.django_db
    def test_creation(self, user):
        profile = Profile.objects.create(user=user, telephone="0612345678")

        assert profile.pk is not None
        assert profile.telephone == "0612345678"

    @pytest.mark.django_db
    def test_str_with_full_name(self):
        u = User.objects.create_user(
            username="jdoe", first_name="Jean", last_name="Doe"
        )
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

    def test_aucun_rattachement_a_un_client(self):
        """Un acteur interne n'appartient à aucun client (09/09) : le champ a"""

        assert not hasattr(Profile, "groupe")


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

    def test_on_delete_client_protect(self):
        assert _get_on_delete(Manifestation, "client") == models.PROTECT

    def test_on_delete_contact_protect(self):
        assert _get_on_delete(Manifestation, "contact") == models.PROTECT

    def test_plus_d_organisateur(self):
        """Remplacé par le contact référent : le client externe n'a pas de"""

        assert not hasattr(Manifestation, "organisateur")

    def test_statut_effectif_brouillon_reste_brouillon(self, manifestation):
        # brouillon est explicite : les dates ne le font pas progresser.
        manifestation.statut = StatutManifestation.BROUILLON
        assert manifestation.statut_effectif == StatutManifestation.BROUILLON
        assert manifestation.accepte_nouvelles_prestations is True

    def test_statut_effectif_planifiee_avant_debut(self, user, client):
        now = timezone.now()
        manif = Manifestation.objects.create(
            nom="Futur camp",
            date_debut=now + timedelta(days=2),
            date_fin=now + timedelta(days=5),
            statut=StatutManifestation.PLANIFIEE,
            client=client,
        )
        assert manif.statut_effectif == StatutManifestation.PLANIFIEE
        assert manif.accepte_nouvelles_prestations is True

    def test_statut_effectif_en_cours_par_dates(self, user, client):
        now = timezone.now()
        manif = Manifestation.objects.create(
            nom="Camp en cours",
            date_debut=now - timedelta(hours=1),
            date_fin=now + timedelta(days=2),
            statut=StatutManifestation.PLANIFIEE,
            client=client,
        )
        assert manif.statut_effectif == StatutManifestation.EN_COURS
        assert manif.accepte_nouvelles_prestations is False

    def test_statut_effectif_terminee_par_dates(self, user, client):
        now = timezone.now()
        manif = Manifestation.objects.create(
            nom="Camp passé",
            date_debut=now - timedelta(days=5),
            date_fin=now - timedelta(days=1),
            statut=StatutManifestation.PLANIFIEE,
            client=client,
        )
        assert manif.statut_effectif == StatutManifestation.TERMINEE
        assert manif.accepte_nouvelles_prestations is False

    def test_statut_effectif_annulee_ignore_les_dates(self, user, client):
        now = timezone.now()
        manif = Manifestation.objects.create(
            nom="Camp annulé",
            date_debut=now - timedelta(hours=1),
            date_fin=now + timedelta(days=2),
            statut=StatutManifestation.ANNULEE,
            client=client,
        )
        # annulée prime sur la dérivation temporelle.
        assert manif.statut_effectif == StatutManifestation.ANNULEE
        assert manif.accepte_nouvelles_prestations is False


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

    def test_on_delete_lieu_protect(self):
        assert _get_on_delete(Prestation, "lieu") == models.PROTECT

    @pytest.mark.django_db
    def test_lieu_reusable_across_prestations(self, manifestation):
        """Un même lieu peut porter plusieurs prestations (base de CON-06)."""

        lieu = Lieu.objects.create(nom="Terrain central")
        presta_a = Prestation.objects.create(
            manifestation=manifestation,
            lieu=lieu,
            nom="A",
            date_debut=manifestation.date_debut,
            date_fin=manifestation.date_debut + timedelta(hours=2),
        )
        presta_b = Prestation.objects.create(
            manifestation=manifestation,
            lieu=lieu,
            nom="B",
            date_debut=manifestation.date_debut,
            date_fin=manifestation.date_debut + timedelta(hours=2),
        )
        assert presta_a.lieu_id == presta_b.lieu_id == lieu.pk
        assert lieu.prestations.count() == 2


# ---------------------------------------------------------------------------
# Lieu
# ---------------------------------------------------------------------------


class TestLieu:
    @pytest.mark.django_db
    def test_creation(self):
        lieu = Lieu.objects.create(
            nom="Prairie nord",
            latitude="48.987654",
            longitude="1.123456",
            capacite=200,
        )
        assert lieu.pk is not None

    @pytest.mark.django_db
    def test_str(self):
        lieu = Lieu.objects.create(nom="Prairie nord")
        assert str(lieu) == "Prairie nord"


# ---------------------------------------------------------------------------
# LignePrestation (RES-09)
# ---------------------------------------------------------------------------


class TestLignePrestation:
    @pytest.mark.django_db
    def test_creation(self, prestation, part):
        from inventree_location.models import LignePrestation

        ligne = LignePrestation.objects.create(
            prestation=prestation, part=part, quantite=3
        )
        assert ligne.pk is not None
        assert str(ligne) == f"part#{part.pk} x3"

    @pytest.mark.django_db
    def test_unique_prestation_part(self, prestation, part):
        from inventree_location.models import LignePrestation

        LignePrestation.objects.create(prestation=prestation, part=part, quantite=1)
        with pytest.raises(IntegrityError), transaction.atomic():
            LignePrestation.objects.create(prestation=prestation, part=part, quantite=2)

    def test_on_delete_prestation_cascade(self):
        from inventree_location.models import LignePrestation

        assert _get_on_delete(LignePrestation, "prestation") == models.CASCADE


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
    def test_client_has_timestamps(self, client):
        assert client.created_at is not None
        assert client.updated_at is not None

    @pytest.mark.django_db
    def test_updated_at_changes(self, client):
        old_updated = client.updated_at
        client.nom = "Nouveau nom"
        client.save()
        client.refresh_from_db()
        assert client.updated_at > old_updated
