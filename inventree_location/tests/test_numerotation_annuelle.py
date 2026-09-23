"""Plafond de la numérotation `RES-AAAA-NNNN`.

Le client annonce 10 000 réservations par an (réponse du 20 mai, ticket
PERF-01). Le compteur était écrit sur quatre chiffres et relu par un tri **de
chaînes** :

    Reservation.objects.filter(numero__startswith="RES-2026-")
        .order_by("-numero").values_list("numero", flat=True).first()

Tant qu'on reste sous 10 000, le zéro de remplissage rend ce tri équivalent à
un tri numérique. À la dix-millième, le numéro passe à cinq chiffres et les deux
ordres divergent : « RES-2026-9999 » est *supérieur* à « RES-2026-10000 » pour
la base, puisque « 9 » vient après « 1 ». Le générateur relisait alors
éternellement 9999, proposait 10000, et se heurtait à la contrainte d'unicité —
cinq fois, puis il abandonnait. La dix-mille-unième réservation de l'année
n'était pas enregistrable, au volume annoncé précisément.

`_generate_reservation_numero` relit désormais un **maximum numérique**, calculé
par la base. Ces tests-là n'insèrent pas dix mille lignes : la bascule ne dépend
que du plus grand numéro présent, une seule ligne suffit à la provoquer.
"""

from __future__ import annotations

import pytest
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

    def test_la_dix_millieme_passe_a_cinq_chiffres(self):
        """La largeur s'étend d'elle-même : quatre chiffres est un minimum."""

        annee = timezone.now().year
        _poser_numero(f"RES-{annee}-9999")

        assert _generate_reservation_numero(annee) == f"RES-{annee}-10000"

    def test_la_dix_mille_unieme_suit_la_dix_millieme(self):
        """Le cas qui bouclait : cinq chiffres déjà posés, on continue.

        Avec un tri de chaînes, « 9999 » repassait devant « 10000 » et le
        générateur reproposait 10000 indéfiniment.
        """

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
        """La conversion en entier est stricte sous PostgreSQL.

        Sans le filtre sur les chiffres, une seule ligne héritée d'une reprise
        de données empêcherait *toute* création ultérieure.
        """

        annee = timezone.now().year
        _poser_numero(f"RES-{annee}-0007")
        _poser_numero(f"RES-{annee}-PROVISOIRE")

        assert _generate_reservation_numero(annee) == f"RES-{annee}-0008"


@pytest.mark.django_db
class TestCoutDeLaGeneration:
    """Le garde-fou : le coût ne doit pas suivre le volume.

    Une mesure en millisecondes dépendrait de la machine ; un nombre de requêtes
    ne dépend de rien. C'est ce qui échouera le jour où quelqu'un remplacera
    l'agrégat par une boucle.
    """

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
