"""Lecture et écriture du `Profile` métier attaché à un utilisateur."""

from django.core.exceptions import ObjectDoesNotExist

from .models import Profile


def user_profile(user):
    """Profil de l'utilisateur, `None` s'il n'en a pas.

    On attrape `ObjectDoesNotExist` et non `Profile.DoesNotExist` : dans le
    conteneur, le chargeur de plugins importe `models` deux fois et les deux
    classes ne coïncident pas.
    """

    if user is None:
        return None

    try:
        return user.location_profile
    except ObjectDoesNotExist:
        return None


def user_phone(user):
    """Téléphone de l'utilisateur, vide s'il n'est pas renseigné."""

    profile = user_profile(user)

    return profile.telephone if profile else ""


def update_user_profile(user, fields):
    """Applique `fields` au profil de l'utilisateur, créé s'il manque."""

    if not fields:
        return None

    profile, _created = Profile.objects.get_or_create(user=user)

    for name, value in fields.items():
        setattr(profile, name, value)

    profile.save()

    # Le `select_related` de la vue a pu mettre en cache le profil d'avant
    # écriture : on vide le cache pour que la relecture reparte de la base.
    user._state.fields_cache.pop("location_profile", None)

    return profile
