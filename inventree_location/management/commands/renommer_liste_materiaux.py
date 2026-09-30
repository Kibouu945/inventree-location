"""Renomme « Liste des matériaux » en « Liste des éléments »."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from inventree_location.traductions import catalogues_francais, remplacer_libelles


def _racines() -> list[Path]:
    """Le catalogue existe deux fois : livré dans l'image, puis collecté."""

    racines = []

    if getattr(settings, "STATIC_ROOT", None):
        racines.append(Path(settings.STATIC_ROOT) / "web")

    # Sans la source, un `collectstatic` ultérieur rétablirait le libellé.
    racines.append(Path(settings.BASE_DIR) / "web" / "static" / "web")

    return racines


class Command(BaseCommand):
    help = (
        "Rewrite the French frontend catalogue of InvenTree so the BOM tab "
        "reads « Liste des éléments » instead of « Liste des matériaux ». "
        "Idempotent: run it after every deployment, and after any InvenTree "
        "upgrade, since the catalogue ships with the image."
    )

    def handle(self, *args, **options):
        catalogues = catalogues_francais(_racines())

        if not catalogues:
            # Soit c'est déjà fait, soit InvenTree a changé de format : les
            # deux méritent un œil, d'où l'avertissement plutôt qu'un succès.
            self.stdout.write(
                self.style.WARNING(
                    "Aucun catalogue à retoucher (déjà renommé, ou format "
                    "InvenTree modifié)."
                )
            )
            return

        total = 0

        for fichier in catalogues:
            contenu, remplacements = remplacer_libelles(
                fichier.read_text(encoding="utf-8")
            )

            if not remplacements:
                continue

            fichier.write_text(contenu, encoding="utf-8")
            total += remplacements
            self.stdout.write(f"  {fichier} : {remplacements} libellé(s)")

        self.stdout.write(self.style.SUCCESS(f"{total} libellé(s) renommé(s) au total"))
