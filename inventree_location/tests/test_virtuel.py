"""Filtre « Virtuel » des prestations et réservations (recette 27/09, 4.5.1)."""

from __future__ import annotations

import pytest

from inventree_location import virtuel


class TestNormaliser:
    @pytest.mark.parametrize("valeur", ["oui", "OUI", " Oui ", "1", "true", "yes"])
    def test_les_ecritures_du_oui(self, valeur):
        assert virtuel.normaliser(valeur) == virtuel.OUI

    @pytest.mark.parametrize("valeur", ["non", "NON", " Non ", "0", "false", "no"])
    def test_les_ecritures_du_non(self, valeur):
        assert virtuel.normaliser(valeur) == virtuel.NON

    @pytest.mark.parametrize("valeur", [None, "", "peut-etre", "tous"])
    def test_le_reste_ne_filtre_pas(self, valeur):
        """Le tableau s'ouvre sans filtre : l'absence doit tout montrer."""

        assert virtuel.normaliser(valeur) is None


@pytest.mark.django_db
class TestFiltrerLesPrestations:
    @pytest.fixture
    def jeu(self):
        from inventree_location.models import LignePrestation, RentableItem
        from inventree_location.tests.factories import (
            make_manifestation,
            make_part,
            make_prestation,
        )

        manifestation = make_manifestation()

        nettoyage = make_part(name="Nettoyage du lieu")
        RentableItem.objects.update_or_create(
            part=nettoyage, defaults={"is_virtual": True}
        )
        table = make_part(name="Table")
        RentableItem.objects.update_or_create(
            part=table, defaults={"is_virtual": False}
        )
        # Article sans fiche location : aucun drapeau à lire.
        sans_fiche = make_part(name="Rallonge")

        fiches = {}

        for cle, parts in {
            "virtuelle": [nettoyage],
            "materielle": [table],
            "mixte": [nettoyage, table],
            "sans_fiche": [sans_fiche],
            "vide": [],
        }.items():
            prestation = make_prestation(manifestation=manifestation, nom=cle)

            for part in parts:
                LignePrestation.objects.create(
                    prestation=prestation, part=part, quantite=1
                )

            fiches[cle] = prestation

        return fiches

    def _noms(self, valeur):
        from inventree_location.models import Prestation

        queryset = virtuel.filtrer(
            Prestation.objects.all(), valeur, lignes="lignes_prestation"
        )

        return set(queryset.values_list("nom", flat=True))

    def test_sans_filtre_tout_est_la(self, jeu):
        assert self._noms(None) == {
            "virtuelle",
            "materielle",
            "mixte",
            "sans_fiche",
            "vide",
        }

    def test_oui_ne_garde_que_le_tout_virtuel(self, jeu):
        assert self._noms("oui") == {"virtuelle"}

    def test_non_ecarte_le_tout_virtuel(self, jeu):
        """Le besoin de la recette : préparer le matériel sans les services."""

        assert "virtuelle" not in self._noms("non")

    def test_une_prestation_mixte_reste_visible_en_non(self, jeu):
        """Elle mobilise du matériel, même si elle porte aussi un service."""

        assert "mixte" in self._noms("non")

    def test_un_article_sans_fiche_compte_comme_materiel(self, jeu):
        """Sinon le filtre masquerait du vrai matériel non encore paramétré."""

        assert "sans_fiche" in self._noms("non")
        assert "sans_fiche" not in self._noms("oui")

    def test_une_prestation_vide_reste_visible_en_non(self, jeu):
        """Une saisie en cours ne doit pas disparaître de l'écran."""

        assert "vide" in self._noms("non")
        assert "vide" not in self._noms("oui")

    def test_les_deux_reponses_partitionnent_la_liste(self, jeu):
        """Rien ne se perd entre « oui » et « non »."""

        oui, non = self._noms("oui"), self._noms("non")

        assert oui | non == self._noms(None)
        assert oui & non == set()

    def test_aucune_ligne_en_double(self, jeu):
        """Une prestation à deux articles ne doit pas sortir deux fois."""

        from inventree_location.models import Prestation

        queryset = virtuel.filtrer(
            Prestation.objects.all(), "non", lignes="lignes_prestation"
        )
        noms = list(queryset.values_list("nom", flat=True))

        assert len(noms) == len(set(noms))


@pytest.mark.django_db
class TestFiltrerLesReservations:
    @pytest.fixture
    def jeu(self):
        from inventree_location.models import LigneReservation, RentableItem
        from inventree_location.tests.factories import make_part, make_reservation

        nettoyage = make_part(name="Nettoyage")
        RentableItem.objects.update_or_create(
            part=nettoyage, defaults={"is_virtual": True}
        )
        table = make_part(name="Table pliante")
        RentableItem.objects.update_or_create(
            part=table, defaults={"is_virtual": False}
        )

        fiches = {}

        for cle, parts in {
            "virtuelle": [nettoyage],
            "materielle": [table],
            "vide": [],
        }.items():
            reservation = make_reservation()

            for part in parts:
                LigneReservation.objects.create(
                    reservation=reservation, part=part, quantite_demandee=1
                )

            fiches[cle] = reservation

        return fiches

    def _numeros(self, valeur, jeu):
        from inventree_location.models import Reservation

        queryset = virtuel.filtrer(Reservation.objects.all(), valeur, lignes="lignes")
        numeros = set(queryset.values_list("numero", flat=True))

        return {cle for cle, resa in jeu.items() if resa.numero in numeros}

    def test_oui_ne_garde_que_le_tout_virtuel(self, jeu):
        assert self._numeros("oui", jeu) == {"virtuelle"}

    def test_non_ecarte_le_tout_virtuel(self, jeu):
        assert self._numeros("non", jeu) == {"materielle", "vide"}
