# --- Surcharge des traductions françaises d'InvenTree (plugin location) ------
# Django fusionne les catalogues de LOCALE_PATHS ; le premier chemin l'emporte.
# On pose donc le nôtre en tête, pour corriger les chaînes du cœur qui rendent
# « Stock » au sens boursier (« Notes sur les transactions boursières »).
# Le chemin est celui du plugin dans l'image, le même que celui monté en dev et
# en prod — si l'emplacement change, le catalogue est simplement ignoré, sans
# rien casser : on préfère perdre la correction que le démarrage.
from pathlib import Path as _CheminLocale

_LOCALE_PLUGIN = _CheminLocale("/home/inventree/plugin/inventree_location/locale")

if _LOCALE_PLUGIN.is_dir():
    LOCALE_PATHS = (_LOCALE_PLUGIN,) + tuple(LOCALE_PATHS)  # noqa: F821
