"""App Django factice fournissant un modèle `Part` minimal pour les tests.

En production, ce label `part` correspond à l'app native d'InvenTree. Ici on
en fournit un strict minimum pour que les FK `"part.Part"` du plugin
résolvent quand la suite tourne hors container InvenTree.
"""

from django.apps import AppConfig


class PartConfig(AppConfig):
    name = "part"
    label = "part"
    verbose_name = "Part (fake for tests)"
