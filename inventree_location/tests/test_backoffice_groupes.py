"""Tests du back-office groupes.

Le modèle `Groupe` n'était éditable que depuis le Django admin : ces vues lui
donnent une surface dans l'application, au même niveau d'accès que le
back-office utilisateurs.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location import roles
from inventree_location.backoffice import (
    BackOfficeGroupeDetailView,
    BackOfficeGroupeListCreateView,
)
from inventree_location.models import Groupe, Profile

User = get_user_model()

GROUPES_URL = "/plugin/inventree-location/backoffice/groupes/"

STRONG_PASSWORD = "Tr0mbone-Aubervilliers"


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def admin(db):
    account = User.objects.create_user(username="patronne", password=STRONG_PASSWORD)
    account.groups.add(Group.objects.get(name=roles.ADMIN))

    return account


def _list(factory, user, **params):
    request = factory.get(GROUPES_URL, params)
    force_authenticate(request, user=user)
    return BackOfficeGroupeListCreateView.as_view()(request)


def _create(factory, user, payload):
    request = factory.post(GROUPES_URL, payload, format="json")
    force_authenticate(request, user=user)
    return BackOfficeGroupeListCreateView.as_view()(request)


def _patch(factory, user, groupe, payload):
    request = factory.patch(f"{GROUPES_URL}{groupe.pk}/", payload, format="json")
    force_authenticate(request, user=user)
    return BackOfficeGroupeDetailView.as_view()(request, pk=groupe.pk)


class TestAcces:
    @pytest.mark.parametrize(
        "role", [roles.GESTIONNAIRE, roles.MAGASINIER, roles.LECTEUR]
    )
    def test_role_non_admin_refuse(self, factory, db, role):
        account = User.objects.create_user(username=f"u-{role}", password=STRONG_PASSWORD)
        account.groups.add(Group.objects.get(name=role))

        assert _list(factory, account).status_code == status.HTTP_403_FORBIDDEN

    def test_admin_autorise(self, factory, admin):
        assert _list(factory, admin).status_code == status.HTTP_200_OK

    def test_superutilisateur_autorise(self, factory, db):
        root = User.objects.create_superuser(
            username="root", email="root@exemple.fr", password=STRONG_PASSWORD
        )

        assert _list(factory, root).status_code == status.HTTP_200_OK


class TestListe:
    def test_liste_triee_avec_nombre_de_membres(self, factory, admin):
        zoulou = Groupe.objects.create(nom="Zoulou", code="ZOU")
        alpha = Groupe.objects.create(nom="Alpha", code="ALP")
        Profile.objects.create(user=admin, groupe=alpha)

        response = _list(factory, admin)

        assert response.status_code == status.HTTP_200_OK
        noms = [item["nom"] for item in response.data["results"]]
        assert noms == [alpha.nom, zoulou.nom]

        membres = {item["nom"]: item["membres"] for item in response.data["results"]}
        assert membres == {"Alpha": 1, "Zoulou": 0}

    def test_recherche_sur_nom_et_code(self, factory, admin):
        Groupe.objects.create(nom="Saint-Exupéry", code="SEX-01")
        Groupe.objects.create(nom="Jeanne d'Arc", code="JDA-02")

        par_nom = _list(factory, admin, search="exup")
        par_code = _list(factory, admin, search="jda")

        assert [item["code"] for item in par_nom.data["results"]] == ["SEX-01"]
        assert [item["nom"] for item in par_code.data["results"]] == ["Jeanne d'Arc"]


class TestCreation:
    def test_creation(self, factory, admin):
        response = _create(
            factory,
            admin,
            {"nom": "Saint-Exupéry", "code": "SEX-01", "adresse": "12 rue du Camp"},
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["membres"] == 0

        groupe = Groupe.objects.get(code="SEX-01")
        assert groupe.nom == "Saint-Exupéry"
        assert groupe.adresse == "12 rue du Camp"

    def test_code_unique(self, factory, admin):
        Groupe.objects.create(nom="Premier", code="DUP")

        response = _create(factory, admin, {"nom": "Second", "code": "DUP"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "code" in response.data

    def test_nom_obligatoire(self, factory, admin):
        response = _create(factory, admin, {"code": "ANO"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "nom" in response.data


class TestEdition:
    def test_renommage(self, factory, admin):
        groupe = Groupe.objects.create(nom="Ancien", code="ANC")

        response = _patch(factory, admin, groupe, {"nom": "Nouveau"})

        assert response.status_code == status.HTTP_200_OK
        groupe.refresh_from_db()
        assert groupe.nom == "Nouveau"
        assert groupe.code == "ANC"

    def test_membres_est_en_lecture_seule(self, factory, admin):
        """`membres` est un compteur annoté : l'envoyer ne doit rien casser."""

        groupe = Groupe.objects.create(nom="Compte", code="CPT")
        Profile.objects.create(user=admin, groupe=groupe)

        response = _patch(factory, admin, groupe, {"membres": 42})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["membres"] == 1