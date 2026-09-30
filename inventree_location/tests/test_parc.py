"""État du parc du magasinier : ce qu'on possède, ce qui est dehors."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from inventree_location import parc


class TestMotifsAlerte:
    def test_rien_a_signaler(self):
        assert parc.motifs_alerte(parc=80, sorti=12, seuil_bas=10) == []

    def test_le_parc_est_tombe_sous_le_seuil(self):
        assert parc.motifs_alerte(parc=3, sorti=0, seuil_bas=5) == ["sous_seuil"]

    def test_sans_seuil_on_ne_signale_pas_la_faiblesse(self):
        """Un article sans seuil n'est pas surveillé : ne rien inventer."""

        assert parc.motifs_alerte(parc=0, sorti=0, seuil_bas=None) == []

    def test_il_est_sorti_plus_que_ce_qu_on_possede(self):
        """Signature d'une réservation forcée, ou de matériel jamais rentré."""

        assert parc.motifs_alerte(parc=4, sorti=6, seuil_bas=None) == [
            "sorti_au_dela_du_parc"
        ]

    def test_les_deux_motifs_se_cumulent(self):
        assert parc.motifs_alerte(parc=2, sorti=6, seuil_bas=5) == [
            "sous_seuil",
            "sorti_au_dela_du_parc",
        ]

    def test_le_seuil_atteint_pile_ne_declenche_pas(self):
        assert parc.motifs_alerte(parc=5, sorti=0, seuil_bas=5) == []


class TestJour:
    def test_un_horodatage_devient_un_jour(self):
        """Le magasinier raisonne au jour : l'heure du retour ne l'intéresse pas."""

        instant = datetime(2026, 10, 11, 18, 30, tzinfo=timezone.utc)
        assert parc._jour(instant) == "2026-10-11"

    def test_une_date_reste_une_date(self):
        assert parc._jour(date(2026, 10, 11)) == "2026-10-11"

    def test_l_absence_de_retour_reste_vide(self):
        assert parc._jour(None) is None


def _part(pk=1, nom="Banc brasserie 220", categorie=None):
    return SimpleNamespace(
        pk=pk,
        name=nom,
        category=SimpleNamespace(name=categorie) if categorie else None,
    )


class TestConstruireLigne:
    def test_la_ligne_complete(self):
        ligne = parc.construire_ligne(
            _part(categorie="Mobilier"),
            parc=80,
            sortie={"sorti": 12, "retour_prevu": datetime(2026, 10, 11, 18, 0)},
            sav=2,
            rentable=SimpleNamespace(seuil_alerte_bas=10, consommable=False),
        )

        assert ligne == {
            "part_id": 1,
            "part_name": "Banc brasserie 220",
            "categorie": "Mobilier",
            "parc": 80,
            "sorti": 12,
            "disponible": 68,
            "retour_prevu": "2026-10-11",
            "sav": 2,
            "seuil_alerte_bas": 10,
            "consommable": False,
            "motifs_alerte": [],
        }

    def test_sans_sortie_tout_le_parc_est_disponible(self):
        ligne = parc.construire_ligne(_part(), parc=40, sortie=None, sav=0)

        assert ligne["sorti"] == 0
        assert ligne["disponible"] == 40
        assert ligne["retour_prevu"] is None

    def test_le_disponible_ne_descend_jamais_sous_zero(self):
        """Six sortis pour quatre en stock : on affiche zéro, pas moins deux.

        Le dépassement est dit par le motif d'alerte, pas par un nombre négatif
        qui laisserait croire à une erreur de calcul.
        """

        ligne = parc.construire_ligne(_part(), parc=4, sortie={"sorti": 6}, sav=0)

        assert ligne["disponible"] == 0
        assert ligne["motifs_alerte"] == ["sorti_au_dela_du_parc"]

    def test_un_article_sans_categorie_ne_plante_pas(self):
        assert (
            parc.construire_ligne(_part(), parc=1, sortie=None, sav=0)["categorie"]
            == ""
        )

    def test_un_article_sans_fiche_louable_n_a_pas_de_seuil(self):
        ligne = parc.construire_ligne(
            _part(), parc=1, sortie=None, sav=0, rentable=None
        )

        assert ligne["seuil_alerte_bas"] is None
        assert ligne["consommable"] is False


class TestChargementsVides:
    """Sans article, on ne part pas interroger la base."""

    @pytest.mark.parametrize("charger", [parc.charger_sorties, parc.charger_sav])
    def test_une_liste_vide_ne_touche_pas_la_base(self, charger):
        assert charger([]) == {}
