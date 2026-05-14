"""Django config for the InvenTreeLocation plugin."""

from django.apps import AppConfig


class InvenTreeLocationConfig(AppConfig):
    """Config class for the InvenTreeLocation plugin."""

    name = "inventree_location"

    def ready(self):
        """This function is called whenever the InvenTreeLocation plugin is loaded."""
        ...
