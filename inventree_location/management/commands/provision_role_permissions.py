from django.core.management.base import BaseCommand

from inventree_location.permissions_provisioning import apply_role_permissions


class Command(BaseCommand):
    help = (
        "Align the InvenTree permissions (RuleSet) of the plugin role groups "
        "with the matrix declared in roles.ROLE_WRITE_RULESETS. Creates any "
        "missing role group. Idempotent: run it after every deployment."
    )

    def handle(self, *args, **options):
        changed = apply_role_permissions()

        for entry in changed:
            self.stdout.write(f"  {entry}")

        if not changed:
            self.stdout.write(self.style.SUCCESS("Permissions already aligned"))
            return

        self.stdout.write(self.style.SUCCESS(f"Aligned {len(changed)} ruleset(s)"))
