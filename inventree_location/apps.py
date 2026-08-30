"""Django config for the InvenTreeLocation plugin."""

from django.apps import AppConfig


class InvenTreeLocationConfig(AppConfig):
    """Config class for the InvenTreeLocation plugin."""

    name = "inventree_location"

    def ready(self):
        """This function is called whenever the InvenTreeLocation plugin is loaded."""

        # Enregistre le signal qui pose les widgets du plugin sur le tableau de
        # bord d'un utilisateur à l'attribution d'un rôle. Import ici, et pas
        # en tête de module, pour ne pas toucher aux modèles avant que le
        # registre d'apps soit prêt.
        from . import dashboard_provisioning  # noqa: F401
