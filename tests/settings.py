"""Settings Django minimaux pour exécuter la suite pytest hors InvenTree.

Fournit juste assez d'infrastructure pour que les modèles, vues et serializers
du plugin se chargent : une base SQLite en mémoire, `django.contrib.auth`,
DRF, et une app `part` factice (cf. `tests/part/`) qui mime le modèle natif
d'InvenTree afin que les FK `"part.Part"` résolvent.
"""

SECRET_KEY = "test-only-not-secret"
USE_TZ = True
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
    "part",
    "inventree_location",
]

ROOT_URLCONF = "tests.urls"

# InvenTree expose ses endpoints derrière `TokenAuthentication` ; on garde le
# même garde-fou ici pour que les tests reflètent la prod (401 sans token, pas 403).
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
}
