"""Plafond de la numérotation `RES-AAAA-NNNN`.

Le client annonce 10 000 réservations par an (réponse du 20 mai, ticket
PERF-01). Le compteur, lui, est écrit sur quatre chiffres et relu par un tri
**de chaînes** :

    Reservation.objects.filter(numero__startswith="RES-2026-")
        .order_by("-numero").values_list("numero", flat=True).first()

Tant qu'on reste sous 10 000, le zéro de remplissage rend ce tri équivalent à
un tri numérique. À la dix-millième, le numéro passe à cinq chiffres et les
deux ordres divergent : « RES-2026-9999 » est *supérieur* à
« RES-2026-10000 » pour Postgres, puisque « 9 » vient après « 1 ». Le
générateur relit alors éternellement 9999, propose 10000, et se heurte à la
contrainte d'unicité — cinq fois, puis il abandonne.

Ces tests-là n'insèrent pas dix mille lignes : la bascule ne dépend que du
plus grand numéro présent, une seule ligne suffit à la provoquer.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError
from django.utils import timezone

from inventree_location.models import Reservation, _generate_reservation_numero
from inventree_location.tests.factories import make_prestation, make_user


def _poser_numero(numero: str) -> None:
    """Insère une réservation portant ce numéro, sans passer par `save()`.

    `bulk_create` court-circuite la génération : c'est le seul moyen de placer
    la base dans l'état « 9 999 réservations déjà émises » sans en créer neuf
    mille neuf cent quatre-vingt-dix-neuf.
    """

    Reservation.objects.bulk_create(
        [
            Reservation(
                numero=numero,
                prestation=make_prestation(),
                demandeur=make_user(),
                date_demande=timezone.now(),
            )
        ]
    )


@pytest.mark.django_db
class TestPlafondNumerotation:
    def test_la_suite_est_correcte_sous_le_plafond(self):
        annee = timezone.now().year
        _poser_numero(f"RES-{annee}-0128")

        assert _generate_reservation_numero(annee) == f"RES-{annee}-0129"

    def test_la_dix_millieme_passe_encore(self):
        """Le passage à cinq chiffres se fait sans bruit : c'est le piège."""

        annee = timezone.now().year
        _poser_numero(f"RES-{annee}-9999")

        assert _generate_reservation_numero(annee) == f"RES-{annee}-10000"

    def test_la_dix_mille_unieme_rejoue_un_numero_deja_pris(self):
        """Le tri de chaînes remet 9999 en tête, et la suite repart de 10000."""

        annee = timezone.now().year
        _poser_numero(f"RES-{annee}-9999")
        _poser_numero(f"RES-{annee}-10000")

        assert _generate_reservation_numero(annee) == f"RES-{annee}-10000"

    def test_au_dela_de_dix_mille_la_creation_echoue(self):
        """Le symptôme utilisateur : la réservation n'est plus enregistrable.

        Cinq tentatives, cinq fois le même numéro déjà pris, puis
        `IntegrityError`. C'est la limite dure du volume annoncé par le
        client — atteinte par la numérotation, pas par le serveur.
        """

        annee = timezone.now().year
        _poser_numero(f"RES-{annee}-9999")
        _poser_numero(f"RES-{annee}-10000")

        with pytest.raises(IntegrityError):
            Reservation.objects.create(
                prestation=make_prestation(),
                demandeur=make_user(),
                date_demande=timezone.now(),
            )
