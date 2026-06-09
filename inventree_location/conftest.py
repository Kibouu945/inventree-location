"""Conftest racine du plugin — ignore les tests Django si Django n'est pas installe."""

import importlib

collect_ignore_glob = []

if importlib.util.find_spec("django") is None:
    collect_ignore_glob.append("tests/*")
