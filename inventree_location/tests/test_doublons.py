"""Détection des clients saisis deux fois sous un nom presque identique."""

from __future__ import annotations

import pytest

from inventree_location.doublons import (
    clients_proches,
    normaliser_nom,
    se_ressemblent,
)


class TestNormaliserNom:
    def test_la_casse_ne_compte_pas(self):
        assert normaliser_nom("MAIRIE") == normaliser_nom("mairie")

    def test_les_accents_ne_comptent_pas(self):
        assert normaliser_nom("École des Beaux-Arts") == "ecole des beaux arts"

    def test_les_espaces_superflus_disparaissent(self):
        assert normaliser_nom("  Mairie   de  Vertou ") == "mairie de vertou"

    def test_la_ponctuation_separe(self):
        assert normaliser_nom("Beaux-Arts") == normaliser_nom("Beaux Arts")

    def test_un_nom_vide_reste_vide(self):
        assert normaliser_nom("") == ""


class TestSeRessemblent:
    @pytest.mark.parametrize(
        "autre",
        [
            "mairie de vertou",
            "MAIRIE DE VERTOU",
            "Mairie  de  Vertou",
            "Mairie de Vertou ",
            "Mairie-de-Vertou",
        ],
    )
    def test_les_variantes_d_ecriture_sont_reconnues(self, autre):
        assert se_ressemblent("Mairie de Vertou", autre)

    def test_un_article_en_moins_ne_trompe_pas(self):
        """« Mairie de Vertou » et « Mairie Vertou » : même client."""

        assert se_ressemblent("Mairie de Vertou", "Mairie Vertou")

    def test_deux_clients_distincts_ne_se_confondent_pas(self):
        assert not se_ressemblent("Mairie de Vertou", "Mairie de Nantes")

    def test_un_nom_plus_precis_reste_distinct(self):
        """Une antenne locale n'est pas la maison mère."""

        assert not se_ressemblent("Les Scouts", "Les Scouts de Lyon")

    def test_un_nom_vide_ne_ressemble_a_rien(self):
        assert not se_ressemblent("", "Mairie de Vertou")
        assert not se_ressemblent("Mairie de Vertou", "")


@pytest.mark.django_db
class TestClientsProches:
    def test_retrouve_la_variante_deja_enregistree(self):
        from inventree_location.tests.factories import make_client

        existant = make_client(nom="Mairie de Vertou")
        autre = make_client(nom="Comité des fêtes")

        proches = clients_proches("MAIRIE DE VERTOU", [existant, autre])

        assert proches == [existant]

    def test_ne_rend_rien_sur_un_nom_neuf(self):
        from inventree_location.tests.factories import make_client

        existant = make_client(nom="Mairie de Vertou")

        assert clients_proches("Mairie de Nantes", [existant]) == []
