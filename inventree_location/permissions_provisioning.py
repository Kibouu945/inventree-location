"""Pose les droits InvenTree des groupes de rôles du plugin.

Partie « branchée » du mécanisme dont le calcul reste dans `roles`
(`ROLE_WRITE_RULESETS`, `ruleset_permissions`) pour être testable hors de la
stack.

Le modèle visé, `users.models.RuleSet`, appartient au cœur d'InvenTree : il est
importé tardivement, et son absence (suite pytest, où InvenTree n'est pas
installé) désactive la pose au lieu de casser le chargement de l'app.

Volontairement pas d'appel au démarrage : réécrire les permissions de tous les
groupes à chaque boot lutterait contre un réglage fait à la main dans l'admin.
La pose se déclenche à la demande, via `manage.py provision_role_permissions`,
donc au déploiement.
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import Group

from . import roles

logger = logging.getLogger("inventree")

#: Champs de `RuleSet` que l'on pilote.
_FLAGS = ("can_view", "can_add", "can_change", "can_delete")


def _ruleset_model():
    """Modèle `RuleSet` d'InvenTree, ou None hors de la stack."""

    try:
        from users.models import RuleSet
    except ImportError:
        return None

    return RuleSet


def apply_role_permissions() -> list[str]:
    """Aligne les droits InvenTree des 8 groupes de rôles sur `roles`.

    Retourne la liste des rulesets modifiés, sous la forme
    ``"<rôle>:<ruleset>"``. Idempotent : appelée deux fois de suite, le second
    appel ne touche rien et retourne une liste vide.

    On parcourt les `RuleSet` qu'InvenTree a créés pour le groupe plutôt qu'une
    liste codée en dur : la table des rulesets appartient à l'hôte et bouge
    d'une version à l'autre. Un ruleset inconnu de `roles` retombe en lecture
    seule.
    """

    ruleset_model = _ruleset_model()

    if ruleset_model is None:
        return []

    changed: list[str] = []

    for role in roles.ALL_ROLES:
        group, created = Group.objects.get_or_create(name=role)

        # InvenTree crée les RuleSet manquants sur le `post_save` du groupe.
        # Un groupe tout juste créé n'en a donc aucun avant ce save.
        if created or not ruleset_model.objects.filter(group=group).exists():
            group.save()

        for ruleset in ruleset_model.objects.filter(group=group):
            wanted = roles.ruleset_permissions(role, ruleset.name)

            if all(getattr(ruleset, flag) == wanted[flag] for flag in _FLAGS):
                continue

            for flag in _FLAGS:
                setattr(ruleset, flag, wanted[flag])

            # `RuleSet.save()` complète les droits impliqués (écrire suppose
            # lire) puis sauve le groupe, ce qui rejoue `update_group_roles` et
            # recalcule les permissions Django sous-jacentes.
            ruleset.save()

            changed.append(f"{role}:{ruleset.name}")

    if changed:
        logger.info(
            "inventree-location: droits InvenTree posés sur %d ruleset(s) : %s",
            len(changed),
            ", ".join(changed),
        )

    return changed
