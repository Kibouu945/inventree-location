"""Commande `seed_charrues` : le festival de la démo live."""

from __future__ import annotations

from datetime import timedelta

import pytest

from django.contrib.auth import authenticate
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from inventree_location.conflicts import detect_reservation_conflicts
from inventree_location.models import (
    Client,
    Contact,
    Lieu,
    LigneReservation,
    Manifestation,
    Prestation,
    Reservation,
    StatutReservation,
)
from inventree_location.stock import compute_part_availability_calendar

from part.models import Part

MOT_DE_PASSE = "Charrues!test"


def semer(**options):
    call_command("seed_charrues", mot_de_passe=MOT_DE_PASSE, **options)


def lyre():
    return Part.objects.get(name="Projecteur lyre")


@pytest.mark.django_db
class TestSeedCharrues:
    def test_seme_le_festival_du_cahier_des_charges(self):
        semer()

        assert Client.objects.get().nom == "Les Charrues"
        assert Contact.objects.count() == 2
        assert set(Lieu.objects.values_list("nom", flat=True)) == {
            "Podium Glenmor",
            "Podium Kerouac",
            "Podium Grall",
            "Château de Kerampuil",
        }
        assert Manifestation.objects.get().nom == "Les Vieilles Charrues"
        # Neuf concerts, les loges, les balances.
        assert Prestation.objects.count() == 11
        # Grall soir n'a pas de bon : il se crée pendant la démo.
        assert Reservation.objects.count() == 10

    def test_les_lieux_portent_les_coordonnees_du_cahier(self):
        semer()

        glenmor = Lieu.objects.get(nom="Podium Glenmor")

        assert float(glenmor.latitude) == pytest.approx(48.272757)
        assert float(glenmor.longitude) == pytest.approx(-3.558783)

    def test_les_comptes_se_connectent_avec_le_mot_de_passe_donne(self):
        semer()

        for compte in ("demo_gestionnaire", "demo_magasinier", "demo_livreur"):
            assert authenticate(username=compte, password=MOT_DE_PASSE) is not None

    def test_sans_mot_de_passe_rien_n_est_seme(self, monkeypatch):
        monkeypatch.delenv("CHARRUES_MOT_DE_PASSE", raising=False)

        with pytest.raises(CommandError, match="Mot de passe"):
            call_command("seed_charrues")

        assert not Client.objects.exists()

    def test_refuse_une_base_qui_porte_deja_des_donnees(self):
        Part.objects.create(name="Tente du vrai client")

        with pytest.raises(CommandError, match="instance de démonstration vide"):
            semer()

        assert not Manifestation.objects.exists()

    def test_refuse_de_semer_deux_fois(self):
        semer()

        with pytest.raises(CommandError, match="déjà semé"):
            semer(force=True)

        assert Manifestation.objects.count() == 1

    def test_les_lyres_sont_en_tension_le_jour_des_concerts(self):
        semer()

        aujourd_hui = timezone.localdate()
        jours = compute_part_availability_calendar(
            lyre(), aujourd_hui - timedelta(days=1), aujourd_hui
        )
        veille, jour = jours

        # Loges 2 + Glenmor soir 4 + Kerouac soir 4, sur 12 en stock.
        assert jour["reserved"] == 10
        assert jour["occupation_rate"] > 75
        assert veille["reserved"] == 2

    def test_le_bon_de_grall_soir_bute_sur_les_lyres(self):
        """Le conflit que la démo montre : 4 lyres demandées, 2 restantes."""

        semer()

        prestation = Prestation.objects.get(nom="Podium Grall — concert du soir")
        bon = Reservation.objects.create(
            prestation=prestation,
            demandeur=Reservation.objects.first().demandeur,
            statut=StatutReservation.SOUMISE,
            date_retrait_prevue=prestation.date_debut - timedelta(hours=2),
            date_retour_prevue=prestation.date_fin,
        )
        LigneReservation.objects.create(reservation=bon, part=lyre(), quantite_demandee=4)

        resultat = detect_reservation_conflicts(bon)

        assert resultat["has_conflict"] is True
        assert resultat["conflicts"][0]["missing_quantity"] == 2

    def test_les_balances_sont_livrees_et_pretes_au_ramassage(self):
        semer()

        balances = Reservation.objects.get(prestation__nom__endswith="balances")
        livre = {
            ligne.part.name: ligne.quantite_livree for ligne in balances.lignes.all()
        }

        assert balances.statut == StatutReservation.LIVREE
        # De quoi déclarer 2 micros détruits, 5 multiprises en SAV, 10 câbles manquants.
        assert livre["Micro HF main"] == 12
        assert livre["Multiprise 6 prises"] == 20
        assert livre["Câble électrique 20 m"] == 40
