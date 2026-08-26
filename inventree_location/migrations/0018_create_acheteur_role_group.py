"""SCRUM-112 : crée le groupe du rôle « acheteur ».

Le rôle était déclaré dans `roles.ALL_ROLES` et référencé par le RBAC des
widgets, mais aucune migration ne créait son groupe : aucun utilisateur ne
pouvait le porter, et `test_all_role_groups_exist` échouait.

Même contrat que `0003_create_role_groups` : groupe sans permissions Django
attachées, l'autorisation restant portée par les permissions DRF. Migration
idempotente et réversible.
"""

from django.db import migrations

ROLE_GROUP = "acheteur"


def create_acheteur_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=ROLE_GROUP)


def remove_acheteur_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=ROLE_GROUP).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("inventree_location", "0017_scrum112_sav_stock_reel"),
        ("auth", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_acheteur_group, remove_acheteur_group),
    ]
