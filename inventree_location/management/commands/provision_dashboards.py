from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from inventree_location.dashboard_provisioning import apply_dashboard


class Command(BaseCommand):
    help = (
        "Place the plugin dashboard widgets on the profile of every user "
        "holding a plugin role (backfill for accounts created before the "
        "automatic provisioning)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            help="Only provision this account instead of every role holder",
        )

    def handle(self, *args, **options):
        users = get_user_model().objects.all()

        if options.get("username"):
            users = users.filter(username=options["username"])

        updated = 0

        for user in users.prefetch_related("groups"):
            if apply_dashboard(user):
                updated += 1
                self.stdout.write(f"  {user.username}")

        self.stdout.write(self.style.SUCCESS(f"Provisioned {updated} dashboard(s)"))
