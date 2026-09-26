"""Photo d'un objet depuis le back-office Parts."""

from __future__ import annotations

import io

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from part.models import Part
from PIL import Image
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location import roles
from inventree_location.part_backoffice import (
    PartBackOfficeDetailView,
    PartBackOfficeImageView,
)
from inventree_location.serializers import CatalogPartSerializer

User = get_user_model()

IMAGE_URL = "/plugin/inventree-location/backoffice/parts/{pk}/image/"


def png(nom: str = "tente.png", couleur: str = "red") -> SimpleUploadedFile:
    """Fichier PNG valide — Pillow doit pouvoir l'ouvrir."""

    tampon = io.BytesIO()
    Image.new("RGB", (16, 16), couleur).save(tampon, format="PNG")

    return SimpleUploadedFile(nom, tampon.getvalue(), content_type="image/png")


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def admin(db):
    compte = User.objects.create_user(username="patronne", password="pwd12345")
    compte.groups.add(Group.objects.get(name=roles.ADMIN))
    return compte


@pytest.fixture
def lecteur(db):
    compte = User.objects.create_user(username="curieux", password="pwd12345")
    compte.groups.add(Group.objects.get(name=roles.LECTEUR))
    return compte


@pytest.fixture
def part(db):
    return Part.objects.create(name="Tente 4 places", description="Canadienne")


def deposer(factory, compte, part, fichier):
    """POST multipart de la photo, comme le fait le front."""

    requete = factory.post(
        IMAGE_URL.format(pk=part.pk), {"image": fichier}, format="multipart"
    )
    force_authenticate(requete, user=compte)

    return PartBackOfficeImageView.as_view()(requete, pk=part.pk)


def test_depot_d_une_photo(factory, admin, part):
    """Le cas nominal : l'admin dépose une image, elle est servie par MEDIA."""

    reponse = deposer(factory, admin, part, png())

    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["image_url"].startswith("/media/part_images/")

    part.refresh_from_db()

    assert part.image
    assert part.image.name.startswith("part_images/")


def test_photo_exposee_par_le_formulaire(factory, admin, part):
    """Le détail back-office renvoie l'URL, pour préremplir la modale."""

    deposer(factory, admin, part, png())

    requete = factory.get(f"/plugin/inventree-location/backoffice/parts/{part.pk}/")
    force_authenticate(requete, user=admin)
    reponse = PartBackOfficeDetailView.as_view()(requete, pk=part.pk)

    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["image_url"].startswith("/media/part_images/")


def test_sans_photo_le_formulaire_renvoie_none(factory, admin, part):
    """Pas d'image de remplacement : le front décide quoi afficher."""

    requete = factory.get(f"/plugin/inventree-location/backoffice/parts/{part.pk}/")
    force_authenticate(requete, user=admin)
    reponse = PartBackOfficeDetailView.as_view()(requete, pk=part.pk)

    assert reponse.data["image_url"] is None


def test_un_fichier_qui_n_est_pas_une_image_est_refuse(factory, admin, part):
    """Sinon le fichier serait stocké puis casserait les vignettes."""

    faux = SimpleUploadedFile(
        "devis.pdf", b"%PDF-1.4 pas une image", content_type="application/pdf"
    )

    reponse = deposer(factory, admin, part, faux)

    assert reponse.status_code == status.HTTP_400_BAD_REQUEST
    assert "image" in reponse.data

    part.refresh_from_db()

    assert not part.image


def test_remplacement_de_la_photo(factory, admin, part):
    """Déposer une seconde image remplace la première."""

    deposer(factory, admin, part, png("avant.png", "red"))
    part.refresh_from_db()
    premiere = part.image.name

    deposer(factory, admin, part, png("apres.png", "blue"))
    part.refresh_from_db()

    assert part.image.name != premiere


def test_retrait_de_la_photo(factory, admin, part):
    """DELETE vide le champ *et* supprime le fichier du disque."""

    deposer(factory, admin, part, png())
    part.refresh_from_db()
    stockage, chemin = part.image.storage, part.image.name

    requete = factory.delete(IMAGE_URL.format(pk=part.pk))
    force_authenticate(requete, user=admin)
    reponse = PartBackOfficeImageView.as_view()(requete, pk=part.pk)

    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["image_url"] is None

    part.refresh_from_db()

    assert not part.image
    assert not stockage.exists(chemin)


def test_retrait_sans_photo_ne_casse_pas(factory, admin, part):
    """Idempotent : retirer une photo absente répond quand même 200."""

    requete = factory.delete(IMAGE_URL.format(pk=part.pk))
    force_authenticate(requete, user=admin)
    reponse = PartBackOfficeImageView.as_view()(requete, pk=part.pk)

    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["image_url"] is None


def test_part_inconnue(factory, admin, db):
    """Une Part qui n'existe pas répond 404, pas 500."""

    requete = factory.post(IMAGE_URL.format(pk=99999), {"image": png()}, format="multipart")
    force_authenticate(requete, user=admin)
    reponse = PartBackOfficeImageView.as_view()(requete, pk=99999)

    assert reponse.status_code == status.HTTP_404_NOT_FOUND


def test_acces_reserve_au_role_admin(factory, lecteur, part):
    """Le back-office reste réservé à l'admin (SCRUM-111)."""

    reponse = deposer(factory, lecteur, part, png())

    assert reponse.status_code == status.HTTP_403_FORBIDDEN


def test_catalogue_expose_une_url_utilisable(factory, admin, part):
    """Régression : `str(part.image)` donnait un chemin relatif inexploitable."""

    deposer(factory, admin, part, png())
    part.refresh_from_db()

    url = CatalogPartSerializer(part).data["image_url"]

    assert url.startswith("/media/part_images/")
    assert not url.startswith("part_images/")


def test_catalogue_sans_photo(factory, part):
    """Une Part sans photo n'expose pas d'URL bidon."""

    assert CatalogPartSerializer(part).data["image_url"] is None
