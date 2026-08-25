from django.core.management.base import BaseCommand

from inventree_location.archiving import archive_old_reservations


class Command(BaseCommand):
    help = "Flag closed reservations older than two years as archived"

    def handle(self, *args, **options):
        count = archive_old_reservations()
        self.stdout.write(self.style.SUCCESS(f"Archived {count} reservations"))
