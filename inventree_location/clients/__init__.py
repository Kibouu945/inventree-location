"""Clients HTTP utilisés par le plugin InvenTreeLocation."""

from __future__ import annotations

import os

from .inventree_client import InvenTreeAPIError, InvenTreeClient

__all__ = ["InvenTreeAPIError", "InvenTreeClient", "get_default_client"]


def get_default_client() -> InvenTreeClient:
    """Instancie un `InvenTreeClient` à partir de la configuration ambiante."""

    base_url = _read_config("INVENTREE_API_URL")
    token = _read_config("INVENTREE_API_TOKEN")
    if not base_url or not token:
        raise RuntimeError(
            "INVENTREE_API_URL et INVENTREE_API_TOKEN doivent être définis "
            "(settings Django ou variables d'environnement)."
        )
    return InvenTreeClient(base_url=base_url, token=token)


def _read_config(name: str) -> str | None:
    """Lit `name` depuis les settings Django, ou à défaut depuis l'environnement."""

    value = None
    try:
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured
    except ImportError:
        pass
    else:
        try:
            value = getattr(settings, name, None)
        except ImproperlyConfigured:
            value = None

    if value:
        return value
    return os.environ.get(name)
