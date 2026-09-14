"""Back-office clients et contacts.

Anciennement le back-office « groupes ». Le point du 09/09/2026 a fait du client
une personne morale et de chaque interlocuteur un `Contact` — sans compte, le
client externe n'accédant pas à la plateforme.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location import roles
from inventree_location.backoffice import (
    BackOfficeClientDetailView,
    BackOfficeClientListCreateView,
    BackOfficeContactDetailView,
    BackOfficeContactListCreateView,
)
from inventree_location.models import Client, Contact

User = get_user_model()

CLIENTS_URL = "/plugin/inventree-location/backoffice/clients/"
CONTACTS_URL = "/plugin/inventree-location/backoffice/contacts/"

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
    request = factory.get(CLIENTS_URL, params)
    force_authenticate(request, user=user)
    return BackOfficeClientListCreateView.as_view()(request)


def _create(factory, user, payload):
    request = factory.post(CLIENTS_URL, payload, format="json")
    force_authenticate(request, user=user)
    return BackOfficeClientListCreateView.as_view()(request)


def _patch(factory, user, client, payload):
    request = factory.patch(f"{CLIENTS_URL}{client.pk}/", payload, format="json")
    force_authenticate(request, user=user)
    return BackOfficeClientDetailView.as_view()(request, pk=client.pk)


def _list_contacts(factory, user, **params):
    request = factory.get(CONTACTS_URL, params)
    force_authenticate(request, user=user)
    return BackOfficeContactListCreateView.as_view()(request)


def _create_contact(factory, user, payload):
    request = factory.post(CONTACTS_URL, payload, format="json")
    force_authenticate(request, user=user)
    return BackOfficeContactListCreateView.as_view()(request)


def _patch_contact(factory, user, contact, payload):
    request = factory.patch(f"{CONTACTS_URL}{contact.pk}/", payload, format="json")
    force_authenticate(request, user=user)
    return BackOfficeContactDetailView.as_view()(request, pk=contact.pk)


class TestAcces:
    @pytest.mark.parametrize("role", [roles.MAGASINIER, roles.LECTEUR, roles.LIVREUR])
    def test_role_sans_relation_client_refuse(self, factory, db, role):
        account = User.objects.create_user(
            username=f"u-{role}", password=STRONG_PASSWORD
        )
        account.groups.add(Group.objects.get(name=role))

        assert _list(factory, account).status_code == status.HTTP_403_FORBIDDEN

    def test_gestionnaire_autorise(self, factory, db):
        """R5 : « un gestionnaire client gère un ou plusieurs clients ».

        Le fichier clients est son outil de travail — il le tient au téléphone.
        Lui refuser l'accès l'obligeait à demander à un administrateur
        d'enregistrer son propre interlocuteur.
        """

        account = User.objects.create_user(
            username="gestionnaire-fichier", password=STRONG_PASSWORD
        )
        account.groups.add(Group.objects.get(name=roles.GESTIONNAIRE))

        assert _list(factory, account).status_code == status.HTTP_200_OK

    def test_gestionnaire_cree_un_client(self, factory, db):
        account = User.objects.create_user(
            username="gestionnaire-createur", password=STRONG_PASSWORD
        )
        account.groups.add(Group.objects.get(name=roles.GESTIONNAIRE))

        request = factory.post(
            CLIENTS_URL,
            {"nom": "Festival du Lac", "type_client": "entreprise"},
            format="json",
        )
        force_authenticate(request, user=account)
        response = BackOfficeClientListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert Client.objects.filter(nom="Festival du Lac").exists()

    def test_admin_autorise(self, factory, admin):
        assert _list(factory, admin).status_code == status.HTTP_200_OK

    def test_superutilisateur_autorise(self, factory, db):
        root = User.objects.create_superuser(
            username="root", email="root@exemple.fr", password=STRONG_PASSWORD
        )

        assert _list(factory, root).status_code == status.HTTP_200_OK

    def test_contacts_suivent_les_clients(self, factory, db):
        """Les contacts vont avec le fichier : c'est le même geste métier.

        Ouvrir les clients au gestionnaire sans leurs interlocuteurs l'aurait
        laissé créer une fiche qu'il ne peut pas remplir — une manifestation
        demande un contact référent.
        """

        account = User.objects.create_user(username="gest", password=STRONG_PASSWORD)
        account.groups.add(Group.objects.get(name=roles.GESTIONNAIRE))

        assert _list_contacts(factory, account).status_code == status.HTTP_200_OK

    def test_contacts_refuses_au_magasinier(self, factory, db):
        account = User.objects.create_user(username="mag", password=STRONG_PASSWORD)
        account.groups.add(Group.objects.get(name=roles.MAGASINIER))

        assert (
            _list_contacts(factory, account).status_code
            == status.HTTP_403_FORBIDDEN
        )


class TestListeClients:
    def test_liste_triee_avec_nombre_de_contacts(self, factory, admin):
        zoulou = Client.objects.create(nom="Zoulou")
        alpha = Client.objects.create(nom="Alpha")
        Contact.objects.create(client=alpha, nom="Durand", prenom="Paul")

        response = _list(factory, admin)

        assert response.status_code == status.HTTP_200_OK
        noms = [item["nom"] for item in response.data["results"]]
        assert noms == [alpha.nom, zoulou.nom]

        contacts = {item["nom"]: item["contacts"] for item in response.data["results"]}
        assert contacts == {"Alpha": 1, "Zoulou": 0}

    def test_gestionnaire_referent_nomme(self, factory, admin):
        """L'écran liste le référent sans avoir à rappeler l'API utilisateurs."""

        referent = User.objects.create_user(
            username="hanane",
            password=STRONG_PASSWORD,
            first_name="Hanane",
            last_name="Bousso",
        )
        Client.objects.create(nom="Alpha", gestionnaire=referent)

        response = _list(factory, admin)

        ligne = response.data["results"][0]
        assert ligne["gestionnaire"] == referent.pk
        assert ligne["gestionnaire_nom"] == "Hanane Bousso (hanane)"

    def test_client_sans_gestionnaire_rend_une_chaine_vide(self, factory, admin):
        Client.objects.create(nom="Alpha")

        response = _list(factory, admin)

        assert response.data["results"][0]["gestionnaire_nom"] == ""

    def test_recherche_sur_nom_et_email(self, factory, admin):
        Client.objects.create(nom="Saint-Exupéry", email="sex@exemple.test")
        Client.objects.create(nom="Jeanne d'Arc", email="jda@exemple.test")

        par_nom = _list(factory, admin, search="exup")
        par_email = _list(factory, admin, search="jda")

        assert [item["nom"] for item in par_nom.data["results"]] == ["Saint-Exupéry"]
        assert [item["nom"] for item in par_email.data["results"]] == ["Jeanne d'Arc"]


class TestCreationClient:
    def test_creation(self, factory, admin):
        response = _create(
            factory,
            admin,
            {
                "nom": "Saint-Exupéry",
                "adresse": "12 rue du Camp",
                "email": "contact@saint-ex.test",
                "telephone": "0611223344",
                "type_client": "entreprise",
                "siret": "12345678900011",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["contacts"] == 0

        client = Client.objects.get(email="contact@saint-ex.test")
        assert client.nom == "Saint-Exupéry"
        assert client.adresse == "12 rue du Camp"
        assert client.actif is True

    def test_email_unique(self, factory, admin):
        Client.objects.create(nom="Premier", email="doublon@exemple.test")

        response = _create(
            factory, admin, {"nom": "Second", "email": "doublon@exemple.test"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data

    def test_email_facultatif(self, factory, admin):
        """Les clients repris n'en avaient pas : on n'en invente pas."""

        response = _create(factory, admin, {"nom": "Sans adresse"})

        assert response.status_code == status.HTTP_201_CREATED
        assert Client.objects.get(nom="Sans adresse").email is None

    def test_nom_obligatoire(self, factory, admin):
        response = _create(factory, admin, {"email": "anonyme@exemple.test"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "nom" in response.data


class TestEditionClient:
    def test_renommage(self, factory, admin):
        client = Client.objects.create(nom="Ancien", email="ancien@exemple.test")

        response = _patch(factory, admin, client, {"nom": "Nouveau"})

        assert response.status_code == status.HTTP_200_OK
        client.refresh_from_db()
        assert client.nom == "Nouveau"
        assert client.email == "ancien@exemple.test"

    def test_desactivation(self, factory, admin):
        """On désactive, on ne supprime pas — question d'historique."""

        client = Client.objects.create(nom="Parti")

        response = _patch(factory, admin, client, {"actif": False})

        assert response.status_code == status.HTTP_200_OK
        client.refresh_from_db()
        assert client.actif is False

    def test_contacts_est_en_lecture_seule(self, factory, admin):
        """`contacts` est un compteur : l'envoyer ne doit rien casser."""

        client = Client.objects.create(nom="Compte")
        Contact.objects.create(client=client, nom="Durand")

        response = _patch(factory, admin, client, {"contacts": 42})

        assert response.status_code == status.HTTP_200_OK


class TestContacts:
    def test_creation(self, factory, admin):
        client = Client.objects.create(nom="Mairie")

        response = _create_contact(
            factory,
            admin,
            {
                "client": client.pk,
                "nom": "Khan",
                "prenom": "Albert",
                "email": "a.khan@exemple.test",
                "telephone": "0622334455",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Contact.objects.get(email="a.khan@exemple.test").client == client

    def test_nom_du_client_expose(self, factory, admin):
        """La liste tous clients confondus doit nommer le client, pas son id."""

        client = Client.objects.create(nom="Mairie de Tassin")
        Contact.objects.create(client=client, nom="Durand")

        response = _list_contacts(factory, admin)

        ligne = response.data["results"][0]
        assert ligne["client"] == client.pk
        assert ligne["client_nom"] == "Mairie de Tassin"

    def test_filtre_par_client(self, factory, admin):
        premier = Client.objects.create(nom="Premier")
        second = Client.objects.create(nom="Second")
        Contact.objects.create(client=premier, nom="Durand")
        Contact.objects.create(client=second, nom="Martin")

        response = _list_contacts(factory, admin, client=premier.pk)

        assert [item["nom"] for item in response.data["results"]] == ["Durand"]

    def test_recherche(self, factory, admin):
        client = Client.objects.create(nom="Mairie")
        Contact.objects.create(client=client, nom="Durand", prenom="Paul")
        Contact.objects.create(client=client, nom="Martin", prenom="Alice")

        response = _list_contacts(factory, admin, search="ali")

        assert [item["nom"] for item in response.data["results"]] == ["Martin"]

    def test_desactivation(self, factory, admin):
        """Un contact qui part sort des listes sans disparaître des devis
        qu'il a signés."""

        client = Client.objects.create(nom="Mairie")
        contact = Contact.objects.create(client=client, nom="Durand")

        response = _patch_contact(factory, admin, contact, {"actif": False})

        assert response.status_code == status.HTTP_200_OK
        contact.refresh_from_db()
        assert contact.actif is False
