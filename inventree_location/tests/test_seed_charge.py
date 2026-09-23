"""Commande `seed_charge` : jeu de données de volume.

Un générateur de charge qui se trompe rend la mesure fausse sans le dire :
des réservations sans lignes ne coûtent rien à arbitrer, un cumul qui recrée
tout à chaque palier mesure la génération plutôt que le serveur, et un
`--reset` trop large emporterait le jeu de démonstration.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command

from inventree_location.management.commands.seed_charge import MARQUEUR
from inventree_location.models import (
    Client,
    LigneReservation,
    Manifestation,
    Prestation,
    Reservation,
    StatutReservation,
)
from inventree_location.tests.factories import creer_chaine


@pytest.mark.django_db
class TestSeedCharge:
    def test_cree_le_volume_demande(self):
        call_command(
            "seed_charge", "--total", "40", "--articles", "6", "--clients", "4"
        )

        assert Reservation.objects.count() == 40
        # Chaque réservation porte sa prestation, et chaque prestation ses
        # lignes : sans elles, la détection de conflit n'aurait rien à lire et
        # la mesure serait celle d'une base vide.
        assert Prestation.objects.count() == 40
        assert LigneReservation.objects.count() >= 40

    def test_le_cumul_complete_au_lieu_de_recreer(self):
        call_command(
            "seed_charge", "--total", "20", "--articles", "6", "--clients", "4"
        )
        premiers = set(Reservation.objects.values_list("numero", flat=True))

        call_command(
            "seed_charge", "--total", "50", "--articles", "6", "--clients", "4"
        )

        assert Reservation.objects.count() == 50
        assert premiers <= set(Reservation.objects.values_list("numero", flat=True))

    def test_le_cumul_reprend_hors_debut_de_groupe(self):
        """Reprise à un indice qui ne tombe pas sur une manifestation neuve.

        20 n'est pas un multiple de 3 : la première réservation du second
        passage doit se rattacher à une manifestation créée pour elle, et non
        à une liste encore vide.
        """

        call_command(
            "seed_charge", "--total", "20", "--articles", "6", "--clients", "4"
        )
        call_command(
            "seed_charge", "--total", "21", "--articles", "6", "--clients", "4"
        )

        assert Reservation.objects.count() == 21
        assert not Prestation.objects.filter(manifestation__isnull=True).exists()

    def test_les_statuts_ne_sont_pas_tous_bloquants(self):
        """Une base entièrement clôturée ne mesurerait aucun arbitrage."""

        call_command(
            "seed_charge", "--total", "120", "--articles", "6", "--clients", "4"
        )

        statuts = set(Reservation.objects.values_list("statut", flat=True))

        assert (
            StatutReservation.VALIDEE in statuts or StatutReservation.SOUMISE in statuts
        )

    def test_le_reset_epargne_ce_qui_n_est_pas_de_la_charge(self):
        chaine = creer_chaine()

        call_command(
            "seed_charge", "--total", "20", "--articles", "6", "--clients", "4"
        )
        call_command("seed_charge", "--total", "0", "--reset")

        assert Reservation.objects.filter(pk=chaine["reservation"].pk).exists()
        assert not Reservation.objects.filter(
            numero__startswith=f"{MARQUEUR}-"
        ).exists()
        assert not Client.objects.filter(nom__startswith=f"{MARQUEUR} ").exists()
        assert not Manifestation.objects.filter(nom__startswith=f"{MARQUEUR} ").exists()
