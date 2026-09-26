"""Historise les pénuries en cours qui ne figurent pas encore au registre."""

from django.core.management.base import BaseCommand

from inventree_location.conflicts import sync_conflict_registry


class Command(BaseCommand):
    help = "Ouvre au registre les conflits de stock en cours non historisés."

    def handle(self, *args, **options):
        ouvertes = sync_conflict_registry()

        self.stdout.write(
            self.style.SUCCESS(f"{ouvertes} conflit(s) ajouté(s) au registre.")
        )
