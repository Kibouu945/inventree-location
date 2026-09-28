"""Redéploie le static du plugin dans le répertoire que sert InvenTree.

`collectstatic` ignore le static d'un plugin, et `make up` recrée le conteneur
serveur : sans cette copie, l'écran reste sur la version précédente.

On purge avant de copier. InvenTree collecte aussi le static au démarrage, et
deux passes concurrentes se marchent dessus : l'une vide le répertoire pendant
que l'autre y écrit. Le résultat est un mélange de deux builds — plus de
fichiers que la source, et pourtant des manquants — qui se voit à l'écran en
« Error Loading Plugin Content / Failed to load module », un 404 sur un bundle.
"""

import shutil
from pathlib import Path

import inventree_location
from django.conf import settings
from plugin.staticfiles import copy_plugin_static_files

CLE = "inventree-location"

collecte = Path(settings.STATIC_ROOT) / "plugins" / CLE
shutil.rmtree(collecte, ignore_errors=True)

copy_plugin_static_files(CLE, check_reload=False)

# La source, prise sur le module installé : pas de chemin en dur à maintenir.
source = Path(inventree_location.__file__).parent / "static"
attendus = sum(1 for _ in source.rglob("*") if _.is_file()) if source.is_dir() else None
obtenus = sum(1 for _ in collecte.rglob("*") if _.is_file())

if attendus is not None and attendus != obtenus:
    raise SystemExit(
        f"static incomplet : {obtenus} fichier(s) collecté(s) pour {attendus} "
        f"à la source ({source}). Relancer `make static`."
    )

print(f"static du plugin : {obtenus} fichier(s) déployé(s).")
