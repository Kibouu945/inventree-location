from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from inventree_location.dashboard_provisioning import apply_dashboard, apply_language


class Command(BaseCommand):
    help = (
        "Place the plugin dashboard widgets and the default interface "
        "language on the profile of every user holding a plugin role "
        "(backfill for accounts created before the automatic provisioning)"
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
        langues = 0

        for user in users.prefetch_related("groups"):
            touched = []

            if apply_dashboard(user):
                updated += 1
                touched.append("dashboard")

            # La langue est posée indépendamment des widgets : un compte peut
            # avoir déjà sa disposition et être resté en anglais, ce qui livre
            # l'interface à la traduction automatique du navigateur.
            if apply_language(user):
                langues += 1
                touched.append("language")

            if touched:
                self.stdout.write(f"  {user.username} ({', '.join(touched)})")

        self.stdout.write(
            self.style.SUCCESS(
                f"Provisioned {updated} dashboard(s) and {langues} language(s)"
            )
        )
