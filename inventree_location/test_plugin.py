"""Tests for the InvenTreeLocation plugin."""

from inventree_location import PLUGIN_VERSION


class TestPluginVersion:
    def test_version_format(self):
        """Version follows semver format."""
        parts = PLUGIN_VERSION.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


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
