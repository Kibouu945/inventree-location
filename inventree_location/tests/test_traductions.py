"""Retouches du catalogue français d'InvenTree (recettes du 7 et du 27/09).

Deux besoins : renommer « Liste des matériaux » en « Liste des éléments », et
traduire les chaînes du module BOM qu'InvenTree ne traduit dans aucune langue.
"""

from __future__ import annotations

from inventree_location.traductions import (
    LIBELLES,
    MARQUEURS_FRANCAIS,
    catalogues_francais,
    remplacer_libelles,
)

#: Forme réelle d'un catalogue Lingui compilé : des clés courtes vers un tableau
#: contenant la chaîne traduite.
CATALOGUE = (
    '{"/4gGIX":["Copy to clipboard"],"/637F4":["Liste des matériaux"],'
    '"ko33wx":["Listes de matériaux invalides"],"x1":["Ordres de fabrication"]}'
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
        assert '"x1":["Ordres de fabrication"]' in contenu

    def test_est_idempotent(self):
        """La commande est rejouée à chaque déploiement."""

        une_fois, _ = remplacer_libelles(CATALOGUE)
        deux_fois, nombre = remplacer_libelles(une_fois)

        assert deux_fois == une_fois
        assert nombre == 0

    def test_ne_sait_pas_dire_la_langue_du_contenu(self):
        """La réécriture est aveugle : c'est la SÉLECTION qui protège.

        Depuis qu'on traduit aussi des chaînes anglaises non traduites,
        `remplacer_libelles` toucherait n'importe quel catalogue. Le tri des
        langues est le travail de `catalogues_francais`, pas le sien.
        """

        allemand = '{"/637F4":["Bill of Materials"],"a":["Stückliste"]}'

        contenu, nombre = remplacer_libelles(allemand)

        assert nombre == 1
        assert "Stückliste" in contenu


class TestCataloguesFrancais:
    def test_retient_le_catalogue_francais(self, tmp_path):
        (tmp_path / "messages-aaa.js").write_text(CATALOGUE, encoding="utf-8")
        (tmp_path / "messages-bbb.js").write_text(
            '{"/637F4":["Stückliste"]}', encoding="utf-8"
        )

        trouves = catalogues_francais([tmp_path])

        assert [f.name for f in trouves] == ["messages-aaa.js"]

    def test_epargne_les_autres_langues_malgre_l_anglais_non_traduit(
        self, tmp_path
    ):
        """Le vrai risque : « Bill of Materials » est dans TOUS les catalogues.

        Le reconnaître par les libellés à remplacer traduirait l'allemand en
        français — d'où la reconnaissance par des marqueurs français stables.
        """

        allemand = '{"a":["Stückliste"],"b":["Bill of Materials"]}'
        (tmp_path / "messages-de.js").write_text(allemand, encoding="utf-8")

        assert catalogues_francais([tmp_path]) == []

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

    def test_reste_trouvable_apres_un_premier_renommage(self, tmp_path):
        """Sans quoi une correction ajoutée plus tard ne s'appliquerait jamais.

        C'est ce qui est arrivé aux chaînes du module BOM : le catalogue était
        déjà renommé, donc introuvable, donc jamais retouché.
        """

        renomme, _ = remplacer_libelles(CATALOGUE)
        (tmp_path / "messages-aaa.js").write_text(renomme, encoding="utf-8")

        assert len(catalogues_francais([tmp_path])) == 1


def test_aucune_traduction_ne_ramene_le_mot_ecarte():
    """Garde-fou : une entrée mal recopiée laisserait « matériaux » à l'écran."""

    for apres in LIBELLES.values():
        assert "matériaux" not in apres


def test_chaque_libelle_vise_bien_le_vocabulaire_du_client():
    """Toute entrée part d'un mot écarté et arrive sur « éléments ».

    Trois origines : « matériaux » (le mot que le client refuse), l'anglais non
    traduit par InvenTree, et « nomenclature » — son mot à lui, qu'on n'aligne
    que là où il cohabiterait avec « éléments » sur un même écran.
    """

    origines = ("matériaux", "Bill of Materials", "BOM", "Nomenclature")

    for avant, apres in LIBELLES.items():
        assert any(mot in avant for mot in origines), avant
        assert "élément" in apres


def test_les_marqueurs_ne_sont_jamais_reecrits():
    """Un marqueur réécrit rendrait le catalogue introuvable au passage suivant."""

    for marqueur in MARQUEURS_FRANCAIS:
        reecrit, nombre = remplacer_libelles(marqueur)
        assert nombre == 0
        assert reecrit == marqueur
