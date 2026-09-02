"""Settings Django minimaux pour exécuter la suite pytest hors InvenTree.

Fournit juste assez d'infrastructure pour que les modèles, vues et serializers
du plugin se chargent : une base SQLite en mémoire, `django.contrib.auth`,
DRF, et une app `part` factice (cf. `tests/part/`) qui mime le modèle natif
d'InvenTree afin que les FK `"part.Part"` résolvent.
"""

import tempfile

SECRET_KEY = "test-only-not-secret"
USE_TZ = True

# Le back-office Parts dépose la photo d'un objet (`Part.image`). Sans
# MEDIA_ROOT, Django écrirait les fichiers de test dans le répertoire courant,
# c'est-à-dire dans le repo. On isole dans un dossier temporaire.
MEDIA_ROOT = tempfile.mkdtemp(prefix="inventree-location-media-")
MEDIA_URL = "/media/"
# Même fuseau métier que la stack (INVENTREE_TIMEZONE dans docker-compose).
# Sans ce réglage, Django retombe sur son défaut America/Chicago : la
# disponibilité « du jour », calculée en heure locale, désignait alors une
# autre journée que les fixtures construites en UTC, et les tests basculaient
# au rouge selon l'heure d'exécution.
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
# un TemplateDoesNotExist en test alors qu'InvenTree, lui, active APP_DIRS.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {},
    }
]

# InvenTree active les validateurs de mot de passe par défaut de Django. Le
# back-office utilisateurs (SCRUM-108) s'appuie dessus : sans eux ici, un test
# de politique de mot de passe passerait au vert alors que la prod refuserait
# le compte.
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
