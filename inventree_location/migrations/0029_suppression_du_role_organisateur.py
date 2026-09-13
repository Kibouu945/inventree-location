"""Supprime le groupe `organisateur`.

Le point du 09/09/2026 a tranché : « l'organisateur externe n'a pas
nécessairement besoin d'un accès à la plateforme ; c'est le gestionnaire
commercial qui le représente ». Le rôle n'a plus d'objet — son interlocuteur
est un `Contact`, sans compte.

Suppression **par queryset**, jamais par `group.user_set.clear()` : le manager
de relation émettrait `m2m_changed`, ce qui réveillerait le récepteur de
`dashboard_provisioning` et écrirait widgets et langue pendant la migration. Le
collector de Django, lui, vide la table pivot en SQL brut.

Les comptes qui ne portaient que ce rôle se retrouvent sans rôle métier : ils
ne verront plus aucun poste de travail, et un administrateur doit leur en
attribuer un. Le nombre est journalisé pour qu'il sache combien.
"""

from django.db import migrations

ROLE = "organisateur"


def supprimer(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")

    groupe = Group.objects.filter(name=ROLE).first()

    if groupe is None:
        return

    orphelins = list(
        User.objects.filter(groups=groupe)
        .exclude(
            groups__name__in=[
                "admin",
                "gestionnaire",
                "magasinier",
                "livreur",
                "sav",
                "lecteur",
                "acheteur",
            ]
        )
        .values_list("username", flat=True)
    )

    Group.objects.filter(name=ROLE).delete()

    if orphelins:
        print(
            f"  inventree-location : {len(orphelins)} compte(s) sans rôle après "
            f"la suppression du rôle organisateur : {', '.join(orphelins[:10])}"
        )


def recreer(apps, schema_editor):
    """Recrée le groupe vide : les appartenances, elles, sont perdues."""

    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=ROLE)


class Migration(migrations.Migration):
    dependencies = [
        ("inventree_location", "0028_verrouillage_client"),
        ("auth", "0001_initial"),
    ]

    operations = [migrations.RunPython(supprimer, recreer)]
