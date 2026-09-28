"""Redéploie le static du plugin dans le répertoire que sert InvenTree.

`collectstatic` ignore le static d'un plugin, et `make up` recrée le conteneur
serveur : sans cette copie, l'écran reste sur la version précédente.
"""

from plugin.staticfiles import copy_plugin_static_files

copy_plugin_static_files("inventree-location", check_reload=False)
