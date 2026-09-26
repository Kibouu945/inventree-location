"""Plafond de la numérotation `RES-AAAA-NNNN`."""

from __future__ import annotations

import pytest
from django.utils import timezone

from inventree_location.models import Reservation, _generate_reservation_numero
from inventree_location.tests.factories import make_prestation, make_user


def _poser_numero(numero: str) -> None:
    """Insère une réservation portant ce numéro, sans passer par `save()`."""

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

    def test_la_dix_millieme_passe_a_cinq_chiffres(self):
        """La largeur s'étend d'elle-même : quatre chiffres est un minimum."""

        annee = timezone.now().year
        _poser_numero(f"RES-{annee}-9999")

        assert _generate_reservation_numero(annee) == f"RES-{annee}-10000"

    def test_la_dix_mille_unieme_suit_la_dix_millieme(self):
        """Le cas qui bouclait : cinq chiffres déjà posés, on continue."""

        annee = timezone.now().year
        _poser_numero(f"RES-{annee}-9999")
        _poser_numero(f"RES-{annee}-10000")

        assert _generate_reservation_numero(annee) == f"RES-{annee}-10001"

    def test_au_dela_de_dix_mille_la_creation_reussit(self):
        """Le symptôme utilisateur : la réservation redevient enregistrable."""

        annee = timezone.now().year
        _poser_numero(f"RES-{annee}-9999")
        _poser_numero(f"RES-{annee}-10000")

        reservation = Reservation.objects.create(
            prestation=make_prestation(),
            demandeur=make_user(),
            date_demande=timezone.now(),
        )

        assert reservation.numero == f"RES-{annee}-10001"

    def test_les_millesimes_sont_independants(self):
        """Une année pleine ne déborde pas sur la suivante."""

        _poser_numero("RES-2025-10000")

        assert _generate_reservation_numero(2026) == "RES-2026-0001"

    def test_un_numero_mal_forme_ne_bloque_pas_la_generation(self):
        """La conversion en entier est stricte sous PostgreSQL."""

        annee = timezone.now().year
        _poser_numero(f"RES-{annee}-0007")
        _poser_numero(f"RES-{annee}-PROVISOIRE")

        assert _generate_reservation_numero(annee) == f"RES-{annee}-0008"


@pytest.mark.django_db
class TestCoutDeLaGeneration:
    """Le garde-fou : le coût ne doit pas suivre le volume."""

    def test_la_generation_coute_une_requete_quel_que_soit_le_volume(
        self, django_assert_num_queries
    ):
        annee = timezone.now().year

        with django_assert_num_queries(1):
            _generate_reservation_numero(annee)

        for rang in range(1, 41):
            _poser_numero(f"RES-{annee}-{rang:04d}")

        with django_assert_num_queries(1):
            assert _generate_reservation_numero(annee) == f"RES-{annee}-0041"
