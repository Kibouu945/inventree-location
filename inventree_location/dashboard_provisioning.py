"""Pose les réglages du plugin sur le profil InvenTree d'un utilisateur."""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from . import dashboards

logger = logging.getLogger("inventree")

#: Actions m2m après lesquelles l'appartenance aux groupes est à jour en base.
_APPLIED_ACTIONS = frozenset({"post_add", "post_remove", "post_clear"})


def _profile_for(user):
    """Profil InvenTree de l'utilisateur, créé au besoin, ou None hors stack."""

    try:
        from users.models import UserProfile
    except ImportError:
        return None

    profile, _created = UserProfile.objects.get_or_create(user=user)

    return profile


def apply_dashboard(user) -> bool:
    """Met le tableau de bord de l'utilisateur en accord avec ses rôles."""

    profile = _profile_for(user)

    if profile is None:
        return False

    desired = dashboards.dashboard_state_for_user(user, profile.widgets)

    if desired == profile.widgets:
        return False

    profile.widgets = desired
    profile.save(update_fields=["widgets"])

    logger.info(
        "inventree-location: tableau de bord posé pour %s (%d widgets)",
        user,
        len(desired["widgets"]),
    )

    return True


#: Langue de l'interface posée sur les profils sans préférence.
LANGUE_PAR_DEFAUT = "fr"


def apply_language(user) -> bool:
    """Pose la langue de l'interface si l'utilisateur n'en a pas choisi une."""

    profile = _profile_for(user)

    if profile is None:
        return False

    if profile.language:
        return False

    profile.language = LANGUE_PAR_DEFAUT
    profile.save(update_fields=["language"])

    logger.info(
        "inventree-location: langue %s posée pour %s",
        LANGUE_PAR_DEFAUT,
        user,
    )

    return True


def _affected_users(instance, reverse, pk_set):
    """Utilisateurs concernés par un changement d'appartenance aux groupes."""

    if not reverse:
        # `user.groups.set(...)` / `.add(...)` : l'instance est l'utilisateur.
        return [instance]

    # `group.user_set.add(...)` : l'instance est le groupe, `pk_set` les
    # utilisateurs.
    if not pk_set:
        return []

    return list(get_user_model().objects.filter(pk__in=pk_set))


@receiver(m2m_changed, sender=get_user_model().groups.through)
def sync_dashboard_on_role_change(sender, instance, action, reverse, pk_set, **kwargs):
    """Repose widgets et langue dès qu'un rôle est attribué ou retiré."""

    if action not in _APPLIED_ACTIONS:
        return

    for user in _affected_users(instance, reverse, pk_set):
        try:
            apply_dashboard(user)
            apply_language(user)
        except Exception:
            # Ni le tableau de bord ni la langue ne doivent faire échouer
            # l'attribution du rôle elle-même.
            logger.exception(
                "inventree-location: pose des réglages impossible pour %s",
                user,
            )
