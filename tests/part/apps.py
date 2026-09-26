"""App Django factice fournissant un modèle `Part` minimal pour les tests."""

from django.apps import AppConfig


class PartConfig(AppConfig):
    name = "part"
    label = "part"
    verbose_name = "Part (fake for tests)"
