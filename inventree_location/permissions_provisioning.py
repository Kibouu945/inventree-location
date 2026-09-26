"""Pose les droits InvenTree des groupes de rôles du plugin."""

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
    """Aligne les droits InvenTree des 8 groupes de rôles sur `roles`."""

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
            ruleset.save()

            changed.append(f"{role}:{ruleset.name}")

    if changed:
        logger.info(
            "inventree-location: droits InvenTree posés sur %d ruleset(s) : %s",
            len(changed),
            ", ".join(changed),
        )

    return changed
