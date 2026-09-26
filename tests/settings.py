"""Settings Django minimaux pour exécuter la suite pytest hors InvenTree."""

import tempfile

SECRET_KEY = "test-only-not-secret"
USE_TZ = True

# Le back-office Parts dépose la photo d'un objet (`Part.image`).
MEDIA_ROOT = tempfile.mkdtemp(prefix="inventree-location-media-")
MEDIA_URL = "/media/"
# Même fuseau métier que la stack (INVENTREE_TIMEZONE dans docker-compose).
TIME_ZONE = "Europe/Paris"
DEBUG = False
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "rest_framework.authtoken",
    "part",
    "stock",
    "inventree_location",
]

ROOT_URLCONF = "tests.urls"

# Sans configuration de templates, aucun loader ne trouve
# `inventree_location/templates/` : le rapport de retour PDF (SCRUM-99) rendait
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {},
    }
]

# InvenTree active les validateurs de mot de passe par défaut de Django.
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        )
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# InvenTree expose ses endpoints derrière `TokenAuthentication` ; on garde le
# même garde-fou ici pour que les tests reflètent la prod (401 sans token, pas 403).
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
}
