"""TR-03 : crée les 7 groupes de rôles (admin, gestionnaire, ...).

Les groupes sont créés sans permissions Django attachées : l'autorisation est
gérée au niveau de l'API par les permissions DRF (cf. permissions.py) sur la
base de l'appartenance aux groupes. Migration idempotente et réversible.
"""

from django.db import migrations

ROLE_GROUPS = (
    "admin",
    "gestionnaire",
    "magasinier",
    "livreur",
    "sav",
    "organisateur",
    "lecteur",
)


def create_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in ROLE_GROUPS:
        Group.objects.get_or_create(name=name)


def remove_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=ROLE_GROUPS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("inventree_location", "0002_reservation_resa_periode_statut_idx"),
        ("auth", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_role_groups, remove_role_groups),
    ]
