"""Tests du back-office utilisateurs (SCRUM-108).

Couvre ce que l'endpoint promet et ce qu'il doit refuser :
- accès réservé au rôle `admin` / superutilisateur ;
- création avec affectation de rôles, mot de passe obligatoire et haché ;
- édition qui ne touche que les groupes métier du plugin ;
- garde-fous : politique de mot de passe, pas d'auto-verrouillage.

Même pattern que `test_ramassage_views.py` : `APIRequestFactory` +
`force_authenticate`.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location import roles
from inventree_location.backoffice import (
    BackOfficeRoleListView,
    BackOfficeUserDetailView,
    BackOfficeUserListCreateView,
)
from inventree_location.models import Profile

User = get_user_model()

USERS_URL = "/plugin/inventree-location/backoffice/users/"
ROLES_URL = "/plugin/inventree-location/backoffice/roles/"

#: Assez long et assez peu commun pour passer les validateurs Django.
STRONG_PASSWORD = "Tr0mbone-Aubervilliers"


@pytest.fixture
def factory():
    return APIRequestFactory()


def _make_user(username, role=None, **kwargs):
    account = User.objects.create_user(
        username=username, password=STRONG_PASSWORD, **kwargs
    )

    if role is not None:
        account.groups.add(Group.objects.get(name=role))

    return account


@pytest.fixture
def admin(db):
    return _make_user("patronne", role=roles.ADMIN)


def _list(factory, user, **params):
    request = factory.get(USERS_URL, params)
    force_authenticate(request, user=user)
    return BackOfficeUserListCreateView.as_view()(request)


def _create(factory, user, payload):
    request = factory.post(USERS_URL, payload, format="json")
    force_authenticate(request, user=user)
    return BackOfficeUserListCreateView.as_view()(request)


def _patch(factory, user, target, payload):
    request = factory.patch(f"{USERS_URL}{target.pk}/", payload, format="json")
    force_authenticate(request, user=user)
    return BackOfficeUserDetailView.as_view()(request, pk=target.pk)


class TestAcces:
    @pytest.mark.parametrize(
        "role",
        [roles.GESTIONNAIRE, roles.MAGASINIER, roles.LIVREUR, roles.LECTEUR],
    )
    def test_role_non_admin_refuse(self, factory, db, role):
        user = _make_user(f"user_{role}", role=role)

        assert _list(factory, user).status_code == status.HTTP_403_FORBIDDEN

    def test_admin_autorise(self, factory, admin):
        assert _list(factory, admin).status_code == status.HTTP_200_OK

    def test_superutilisateur_autorise(self, factory, db):
        root = _make_user("root", is_superuser=True)

        assert _list(factory, root).status_code == status.HTTP_200_OK


class TestListe:
    def test_liste_paginee_expose_le_role(self, factory, admin):
        response = _list(factory, admin)

        assert response.data["count"] == 1
        assert response.data["results"][0]["username"] == "patronne"
        assert response.data["results"][0]["role"] == roles.ADMIN

    @pytest.mark.parametrize(
        "terme, attendu",
        [
            ("patronne", 1),
            ("PATRO", 1),
            ("magasin", 1),
            ("inconnu", 0),
        ],
    )
    def test_recherche_sur_username_prenom_nom_email(
        self, factory, admin, terme, attendu
    ):
        _make_user("hakim", first_name="Magasin", last_name="Central")

        response = _list(factory, admin, search=terme)

        assert response.data["count"] == attendu

    def test_un_utilisateur_apparait_une_seule_fois(self, factory, admin):
        """La recherche combine 4 champs : elle ne doit pas dupliquer les lignes."""

        _make_user(
            "doublon",
            first_name="doublon",
            last_name="doublon",
            email="doublon@example.com",
        )

        response = _list(factory, admin, search="doublon")

        assert response.data["count"] == 1


class TestCreation:
    def test_creation_avec_un_role(self, factory, admin):
        response = _create(
            factory,
            admin,
            {
                "username": "nouveau",
                "password": STRONG_PASSWORD,
                "role": roles.MAGASINIER,
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

        created = User.objects.get(username="nouveau")

        assert roles.user_roles(created) == {roles.MAGASINIER}
        # Le mot de passe est haché, jamais stocké en clair.
        assert created.password != STRONG_PASSWORD
        assert created.check_password(STRONG_PASSWORD)

    def test_mot_de_passe_obligatoire(self, factory, admin):
        response = _create(factory, admin, {"username": "sans_mdp"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data

    def test_mot_de_passe_trop_faible_refuse(self, factory, admin):
        """La politique du site s'applique, pas seulement une longueur minimale."""

        response = _create(
            factory, admin, {"username": "faible", "password": "123456"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data

    def test_role_inconnu_refuse(self, factory, admin):
        response = _create(
            factory,
            admin,
            {
                "username": "inventif",
                "password": STRONG_PASSWORD,
                "role": "sorcier",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_is_superuser_non_modifiable(self, factory, admin):
        response = _create(
            factory,
            admin,
            {
                "username": "ambitieux",
                "password": STRONG_PASSWORD,
                "is_superuser": True,
                "is_staff": True,
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

        created = User.objects.get(username="ambitieux")

        assert created.is_superuser is False
        assert created.is_staff is False


class TestEdition:
    def test_changement_de_role(self, factory, admin):
        """Le nouveau rôle remplace l'ancien : un acteur interne n'en porte
        qu'un (décision du 09/09/2026)."""

        cible = _make_user("mutant", role=roles.LECTEUR)

        response = _patch(factory, admin, cible, {"role": roles.SAV})

        assert response.status_code == status.HTTP_200_OK
        assert roles.user_roles(cible) == {roles.SAV}

    def test_le_role_peut_etre_retire(self, factory, admin):
        cible = _make_user("sans-poste", role=roles.LECTEUR)

        response = _patch(factory, admin, cible, {"role": None})

        assert response.status_code == status.HTTP_200_OK
        assert roles.user_roles(cible) == set()

    def test_les_groupes_hors_plugin_sont_conserves(self, factory, admin):
        cible = _make_user("mutant", role=roles.LECTEUR)
        externe = Group.objects.create(name="groupe-inventree-natif")
        cible.groups.add(externe)

        _patch(factory, admin, cible, {"role": roles.SAV})

        assert set(cible.groups.values_list("name", flat=True)) == {
            roles.SAV,
            "groupe-inventree-natif",
        }

    def test_desactivation(self, factory, admin):
        cible = _make_user("indesirable")

        response = _patch(factory, admin, cible, {"is_active": False})

        cible.refresh_from_db()

        assert response.status_code == status.HTTP_200_OK
        assert cible.is_active is False

    def test_mot_de_passe_vide_conserve_lancien(self, factory, admin):
        cible = _make_user("stable")

        _patch(factory, admin, cible, {"password": ""})

        cible.refresh_from_db()

        assert cible.check_password(STRONG_PASSWORD)

    def test_nouveau_mot_de_passe_hache(self, factory, admin):
        cible = _make_user("renouvele")

        _patch(factory, admin, cible, {"password": "Contrebasse-Pantin-42"})

        cible.refresh_from_db()

        assert cible.check_password("Contrebasse-Pantin-42")


class TestAntiVerrouillage:
    """Un admin ne doit pas pouvoir se fermer la porte à lui-même."""

    def test_ne_peut_pas_se_desactiver(self, factory, admin):
        response = _patch(factory, admin, admin, {"is_active": False})

        admin.refresh_from_db()

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert admin.is_active is True

    def test_ne_peut_pas_retirer_son_propre_role_admin(self, factory, admin):
        response = _patch(factory, admin, admin, {"role": roles.LECTEUR})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert roles.user_roles(admin) == {roles.ADMIN}

    def test_peut_desactiver_quelqu_un_dautre(self, factory, admin):
        autre = _make_user("autre", role=roles.ADMIN)

        response = _patch(factory, admin, autre, {"is_active": False})

        assert response.status_code == status.HTTP_200_OK

    def test_peut_se_reaffirmer_admin(self, factory, admin):
        """Renvoyer son propre rôle admin n'est pas un verrouillage."""

        response = _patch(factory, admin, admin, {"role": roles.ADMIN})

        assert response.status_code == status.HTTP_200_OK
        assert roles.user_roles(admin) == {roles.ADMIN}


class TestRoleList:
    def test_liste_des_roles(self, factory, admin):
        request = factory.get(ROLES_URL)
        force_authenticate(request, user=admin)

        response = BackOfficeRoleListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert [item["name"] for item in response.data] == list(roles.ALL_ROLES)
        assert {"name": roles.ACHETEUR, "label": "Acheteur"} in response.data

    def test_les_groupes_de_roles_existent_deja(self, factory, admin):
        """Les migrations les créent : l'endpoint n'a rien à écrire (GET)."""

        assert Group.objects.filter(name__in=roles.ALL_ROLES).count() == len(
            roles.ALL_ROLES
        )


class TestProfil:
    """Le téléphone, porté par le `Profile` et non par le `User`.

    Il s'imprime sur le bon de livraison : sans ce champ, seul le Django admin
    permettait de le renseigner.

    Le rattachement à un client a disparu avec `Profile.groupe` : un acteur
    interne n'appartient à aucun client (09/09/2026).
    """

    def test_creation_avec_telephone(self, factory, admin):
        response = _create(
            factory,
            admin,
            {
                "username": "livreuse",
                "password": STRONG_PASSWORD,
                "telephone": "0102030405",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["telephone"] == "0102030405"
        assert Profile.objects.get(user__username="livreuse").telephone == "0102030405"

    def test_creation_sans_profil_reste_vide(self, factory, admin):
        """Aucun `Profile` inutile : le champ absent ne déclenche pas d'écriture."""

        response = _create(
            factory, admin, {"username": "sobre", "password": STRONG_PASSWORD}
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["telephone"] == ""
        assert not Profile.objects.filter(user__username="sobre").exists()

    def test_edition_cree_le_profil_manquant(self, factory, admin):
        cible = _make_user("magasinier")

        response = _patch(factory, admin, cible, {"telephone": "0605040302"})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["telephone"] == "0605040302"
        assert Profile.objects.get(user=cible).telephone == "0605040302"

    def test_patch_partiel_ne_vide_pas_le_telephone(self, factory, admin):
        cible = _make_user("stable")
        Profile.objects.create(user=cible, telephone="0700000000")

        response = _patch(factory, admin, cible, {"email": "stable@exemple.fr"})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["telephone"] == "0700000000"
        assert Profile.objects.get(user=cible).telephone == "0700000000"

    def test_aucun_rattachement_a_un_client(self, factory, admin):
        """La fiche utilisateur n'expose plus de client : le champ a été retiré
        du modèle, il ne doit pas revenir par le serializer."""

        cible = _make_user("interne")
        Profile.objects.create(user=cible, telephone="0899887766")

        response = _list(factory, admin, search="interne")

        ligne = response.data["results"][0]
        assert "groupe" not in ligne
        assert "groupe_nom" not in ligne

    def test_liste_expose_le_telephone(self, factory, admin):
        cible = _make_user("listee")
        Profile.objects.create(user=cible, telephone="0899887766")

        response = _list(factory, admin, search="listee")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"][0]["telephone"] == "0899887766"
