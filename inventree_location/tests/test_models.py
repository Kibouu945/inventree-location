"""Tests des modeles Django du plugin InvenTreeLocation."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from inventree_location.models import (
    Article,
    Categorie,
    Groupe,
    Lieu,
    LigneReservation,
    Manifestation,
    Mouvement,
    Prestation,
    Profile,
    Reservation,
    StatutManifestation,
    StatutReservation,
    TypeMouvement,
)


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
def categorie(db):
    return Categorie.objects.create(nom="Camping")


@pytest.fixture
def article(groupe, categorie):
    return Article.objects.create(
        reference="ART-001",
        nom="Tente 4 places",
        categorie=categorie,
        groupe=groupe,
        quantite_totale=10,
    )


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
def ligne(reservation, article):
    return LigneReservation.objects.create(
        reservation=reservation,
        article=article,
        quantite_demandee=5,
    )


def _get_on_delete(model, field_name):
    """Retourne la strategie on_delete d'un champ FK."""
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
# Categorie
# ---------------------------------------------------------------------------


class TestCategorie:
    def test_creation(self, categorie):
        assert categorie.pk is not None

    def test_str(self, categorie):
        assert str(categorie) == "Camping"

    @pytest.mark.django_db
    def test_hierarchie(self, categorie):
        enfant = Categorie.objects.create(nom="Tentes", parent=categorie)
        assert enfant.parent == categorie
        assert categorie.enfants.count() == 1

    def test_on_delete_parent_protect(self):
        assert _get_on_delete(Categorie, "parent") == models.PROTECT


# ---------------------------------------------------------------------------
# Article
# ---------------------------------------------------------------------------


class TestArticle:
    def test_creation(self, article):
        assert article.pk is not None
        assert article.quantite_totale == 10
        assert article.unite == "piece"

    def test_str(self, article):
        assert str(article) == "ART-001 — Tente 4 places"

    @pytest.mark.django_db
    def test_reference_unique(self, article, groupe, categorie):
        with pytest.raises(IntegrityError), transaction.atomic():
            Article.objects.create(
                reference="ART-001",
                nom="Doublon",
                categorie=categorie,
                groupe=groupe,
            )

    def test_on_delete_categorie_protect(self):
        assert _get_on_delete(Article, "categorie") == models.PROTECT

    def test_on_delete_groupe_protect(self):
        assert _get_on_delete(Article, "groupe") == models.PROTECT


# ---------------------------------------------------------------------------
# Reservation
# ---------------------------------------------------------------------------


class TestReservation:
    def test_creation(self, reservation):
        assert reservation.pk is not None
        assert reservation.statut == StatutReservation.BROUILLON

    def test_str(self, reservation):
        assert str(reservation) == f"Réservation #{reservation.pk} — Brouillon"

    def test_on_delete_prestation_protect(self):
        assert _get_on_delete(Reservation, "prestation") == models.PROTECT

    def test_on_delete_demandeur_protect(self):
        assert _get_on_delete(Reservation, "demandeur") == models.PROTECT

    def test_on_delete_validateur_protect(self):
        assert _get_on_delete(Reservation, "validateur") == models.PROTECT


# ---------------------------------------------------------------------------
# LigneReservation
# ---------------------------------------------------------------------------


class TestLigneReservation:
    def test_creation(self, ligne):
        assert ligne.pk is not None
        assert ligne.quantite_demandee == 5
        assert ligne.quantite_livree == 0
        assert ligne.quantite_retournee == 0

    def test_str(self, ligne):
        assert str(ligne) == "ART-001 — Tente 4 places x5"

    def test_on_delete_reservation_cascade(self):
        assert _get_on_delete(LigneReservation, "reservation") == models.CASCADE

    def test_on_delete_article_protect(self):
        assert _get_on_delete(LigneReservation, "article") == models.PROTECT

    @pytest.mark.django_db
    def test_unique_constraint(self, reservation, article):
        LigneReservation.objects.create(
            reservation=reservation,
            article=article,
            quantite_demandee=3,
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            LigneReservation.objects.create(
                reservation=reservation,
                article=article,
                quantite_demandee=1,
            )


# ---------------------------------------------------------------------------
# Mouvement
# ---------------------------------------------------------------------------


class TestMouvement:
    @pytest.fixture
    def mouvement(self, article, ligne, user):
        return Mouvement.objects.create(
            article=article,
            ligne_reservation=ligne,
            type=TypeMouvement.SORTIE,
            quantite=-5,
            date=timezone.now(),
            utilisateur=user,
        )

    def test_creation(self, mouvement):
        assert mouvement.pk is not None
        assert mouvement.type == TypeMouvement.SORTIE
        assert mouvement.quantite == -5

    def test_str(self, mouvement):
        assert "Sortie" in str(mouvement)
        assert "-5" in str(mouvement)

    def test_on_delete_article_protect(self):
        assert _get_on_delete(Mouvement, "article") == models.PROTECT

    def test_on_delete_ligne_cascade(self):
        assert _get_on_delete(Mouvement, "ligne_reservation") == models.CASCADE

    def test_on_delete_utilisateur_set_null(self):
        assert _get_on_delete(Mouvement, "utilisateur") == models.SET_NULL

    @pytest.mark.django_db
    def test_creation_sans_ligne(self, article, user):
        mouvement = Mouvement.objects.create(
            article=article,
            type=TypeMouvement.AJUSTEMENT,
            quantite=10,
            date=timezone.now(),
            utilisateur=user,
        )
        assert mouvement.ligne_reservation is None


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
