"""Crée le groupe de rôle « acheteur », ajouté à ``roles.ALL_ROLES`` après TR-03.

Même principe que ``0003_create_role_groups`` : groupe sans permissions Django
attachées, l'autorisation restant portée par les permissions DRF sur la base de
l'appartenance aux groupes. Migration idempotente et réversible.
"""

from django.db import migrations

ROLE_GROUPS = ("acheteur",)


def create_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in ROLE_GROUPS:
        Group.objects.get_or_create(name=name)


def remove_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=ROLE_GROUPS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("inventree_location", "0010_remove_rentableitem_stock_total"),
        ("auth", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_role_groups, remove_role_groups),
    ]
