"""Tests for the InvenTreeLocation plugin."""

from inventree_location import PLUGIN_VERSION


class TestPluginVersion:
    def test_version_commence_par_un_numero_a_trois_chiffres(self):
        """MAJEUR.MINEUR.CORRECTIF en tête, quel que soit ce qui suit.

        La version vient désormais du tag git (`setuptools_scm`). Sur un tag
        elle vaut exactement `1.2.0` ; entre deux tags elle porte la distance et
        le hash — `1.2.1.dev12+g9a3f1c2` —, et sur des sources non installées
        `0.0.0+sources`. Exiger trois composants et rien d'autre reviendrait à
        interdire les deux derniers cas, qui sont précisément ce qui rend une
        version de développement reconnaissable.
        """

        tete = PLUGIN_VERSION.split("+")[0].split(".")

        assert len(tete) >= 3
        assert all(part.isdigit() for part in tete[:3])


class TestPluginStructure:
    def test_core_module_exists(self):
        """Plugin core module is importable (entry point)."""
        import importlib

        spec = importlib.util.find_spec("inventree_location.core")
        assert spec is not None

    def test_models_module_exists(self):
        import importlib

        spec = importlib.util.find_spec("inventree_location.models")
        assert spec is not None

    def test_views_module_exists(self):
        import importlib

        spec = importlib.util.find_spec("inventree_location.views")
        assert spec is not None

    def test_serializers_module_exists(self):
        import importlib

        spec = importlib.util.find_spec("inventree_location.serializers")
        assert spec is not None

    def test_entry_point_registered(self):
        """Plugin is discoverable via entry points."""
        from importlib.metadata import entry_points

        eps = entry_points(group="inventree_plugins")
        slugs = [e.name for e in eps]
        assert "InvenTreeLocation" in slugs
