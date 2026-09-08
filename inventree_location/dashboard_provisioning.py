"""Pose les réglages du plugin sur le profil InvenTree d'un utilisateur.

Partie « branchée » du mécanisme décrit dans `dashboards` : accès base et
signal Django. Le calcul de la disposition, lui, reste dans `dashboards` pour
être testable hors de la stack.

Le modèle visé est `users.models.UserProfile`, qui appartient au cœur
d'InvenTree : il est importé tardivement, et son absence (suite pytest, où
InvenTree n'est pas installé) désactive silencieusement la pose au lieu de
casser le chargement de l'app.
"""

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
    """Profil InvenTree de l'utilisateur, créé au besoin, ou None hors stack.

    Un compte créé en shell peut ne pas avoir de profil (`User has no
    profile`) : on le crée plutôt que de laisser remonter l'exception.
    """

    try:
        from users.models import UserProfile
    except ImportError:
        return None

    profile, _created = UserProfile.objects.get_or_create(user=user)

    return profile


def apply_dashboard(user) -> bool:
    """Met le tableau de bord de l'utilisateur en accord avec ses rôles.

    Retourne True si le profil a été écrit. Idempotent : appelé deux fois de
    suite, le second appel ne touche rien.
    """

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
#:
#: `INVENTREE_LANGUAGE` ne suffit pas : il fixe le `LANGUAGE_CODE` de Django —
#: donc les rendus serveur, les rapports et les e-mails — mais l'interface web
#: d'InvenTree lit `UserProfile.language`, et ce champ est nul sur tout compte
#: neuf. Le shell restait donc en anglais quoi qu'on mette dans
#: l'environnement, Chrome concluait « page anglaise » et traduisait la page
#: entière : nos libellés français réécrits (« Annuler » → « Annuleur »,
#: « Enregistrer » → « Économiser »), les écrans du cœur en charabia
#: (« Parties », « Actions boursières », « Aucune inscription disponible ») et
#: jusqu'aux données saisies (« Zone émargement » affiché « Zone d'émarrage »).
#: Recette Tassin du 07/09/2026, remarques 3, 9 et 12.
LANGUE_PAR_DEFAUT = "fr"


def apply_language(user) -> bool:
    """Pose la langue de l'interface si l'utilisateur n'en a pas choisi une.

    Retourne True si le profil a été écrit. Ne touche jamais à un choix
    existant : c'est un défaut, pas une contrainte — un bénévole anglophone
    doit pouvoir repasser son compte en anglais depuis ses préférences.
    """

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
    # utilisateurs. Sur un `clear()` inverse, `pk_set` est None et le lien est
    # déjà rompu — on ne peut plus savoir qui était concerné, on passe.
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
