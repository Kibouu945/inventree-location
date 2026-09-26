# -*- coding: utf-8 -*-

"""Version du plugin, déduite du tag git."""

try:
    from ._version import version as PLUGIN_VERSION
except ImportError:  # pragma: no cover - dépend de l'installation, pas du code
    PLUGIN_VERSION = "0.0.0+sources"
