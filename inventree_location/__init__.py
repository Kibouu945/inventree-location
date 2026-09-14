# -*- coding: utf-8 -*-

"""Version du plugin, déduite du tag git.

Le numéro n'est plus écrit à la main : `setuptools_scm` le lit sur le tag au
moment de l'installation et écrit `_version.py`, que ce module relit. Poser un
tag suffit donc à livrer la bonne version — c'est la correction d'un écart
survenu deux fois, où le dépôt annonçait 1.0.0 pendant que la prod tournait le
tag 1.1.0.

Hors installation — dépôt cloné, `pytest` sur les sources — le fichier n'existe
pas : on répond alors une version qui se reconnaît au premier regard plutôt que
d'échouer à l'import.
"""

try:
    from ._version import version as PLUGIN_VERSION
except ImportError:  # pragma: no cover - dépend de l'installation, pas du code
    PLUGIN_VERSION = "0.0.0+sources"
