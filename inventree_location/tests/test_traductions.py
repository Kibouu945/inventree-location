"""Renommage du libellé « Liste des matériaux » (recette du 27/09, 4.3.1)."""

from __future__ import annotations

from inventree_location.traductions import (
    LIBELLES,
    catalogues_francais,
    remplacer_libelles,
)

#: Forme réelle d'un catalogue Lingui compilé : des clés courtes vers un tableau
#: contenant la chaîne traduite.
CATALOGUE = (
    '{"/4gGIX":["Copy to clipboard"],"/637F4":["Liste des matériaux"],'
    '"ko33wx":["Listes de matériaux invalides"],"x1":["Autre chose"]}'
)


class TestRemplacerLibelles:
    def test_renomme_l_onglet(self):
        contenu, nombre = remplacer_libelles('["Liste des matériaux"]')

        assert contenu == '["Liste des éléments"]'
        assert nombre == 1

    def test_une_phrase_longue_n_est_pas_coupee_par_une_courte(self):
        """« Liste des matériaux » est un préfixe des autres libellés."""

        contenu, _ = remplacer_libelles('["Listes de matériaux invalides"]')

        assert contenu == '["Listes d\'éléments invalides"]'

    def test_traite_toutes_les_entrees_d_un_catalogue(self):
        contenu, nombre = remplacer_libelles(CATALOGUE)

        assert nombre == 2
        assert "matériaux" not in contenu
        # Le reste du catalogue est rendu intact.
        assert '"/4gGIX":["Copy to clipboard"]' in contenu
        assert '"x1":["Autre chose"]' in contenu

    def test_est_idempotent(self):
        """La commande est rejouée à chaque déploiement."""

        une_fois, _ = remplacer_libelles(CATALOGUE)
        deux_fois, nombre = remplacer_libelles(une_fois)

        assert deux_fois == une_fois
        assert nombre == 0

    def test_ne_touche_pas_un_catalogue_d_une_autre_langue(self):
        anglais = '{"/637F4":["Bill of Materials"]}'

        contenu, nombre = remplacer_libelles(anglais)

        assert contenu == anglais
        assert nombre == 0


class TestCataloguesFrancais:
    def test_retient_le_catalogue_francais(self, tmp_path):
        (tmp_path / "messages-aaa.js").write_text(CATALOGUE, encoding="utf-8")
        (tmp_path / "messages-bbb.js").write_text(
            '{"/637F4":["Bill of Materials"]}', encoding="utf-8"
        )

        trouves = catalogues_francais([tmp_path])

        assert [f.name for f in trouves] == ["messages-aaa.js"]

    def test_descend_dans_les_sous_dossiers(self, tmp_path):
        assets = tmp_path / "assets"
        assets.mkdir()
        (assets / "messages-ccc.js").write_text(CATALOGUE, encoding="utf-8")

        assert len(catalogues_francais([tmp_path])) == 1

    def test_ignore_les_autres_fichiers(self, tmp_path):
        (tmp_path / "index.js").write_text(CATALOGUE, encoding="utf-8")

        assert catalogues_francais([tmp_path]) == []

    def test_une_racine_absente_ne_casse_pas(self, tmp_path):
        assert catalogues_francais([tmp_path / "nexiste-pas"]) == []

    def test_ne_rend_rien_une_fois_le_renommage_fait(self, tmp_path):
        renomme, _ = remplacer_libelles(CATALOGUE)
        (tmp_path / "messages-aaa.js").write_text(renomme, encoding="utf-8")

        assert catalogues_francais([tmp_path]) == []


def test_les_libelles_visent_tous_le_mot_element():
    """Garde-fou : une entrée mal recopiée laisserait « matériaux » à l'écran."""

    for avant, apres in LIBELLES.items():
        assert "matériaux" in avant
        assert "matériaux" not in apres
        assert "élément" in apres
