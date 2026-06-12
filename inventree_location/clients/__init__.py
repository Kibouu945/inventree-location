"""Clients HTTP utilisés par le plugin InvenTreeLocation."""

from __future__ import annotations

import os

from .inventree_client import InvenTreeAPIError, InvenTreeClient

__all__ = ["InvenTreeAPIError", "InvenTreeClient", "get_default_client"]


def get_default_client() -> InvenTreeClient:
    """Instancie un `InvenTreeClient` à partir de la configuration ambiante.

    Lit `INVENTREE_API_URL` et `INVENTREE_API_TOKEN` depuis les settings Django
    en priorité, puis depuis l'environnement. Lève `RuntimeError` si l'un des
    deux est manquant — le client a besoin des deux pour fonctionner.
    """

    base_url = _read_config("INVENTREE_API_URL")
    token = _read_config("INVENTREE_API_TOKEN")
    if not base_url or not token:
        raise RuntimeError(
            "INVENTREE_API_URL et INVENTREE_API_TOKEN doivent être définis "
            "(settings Django ou variables d'environnement)."
        )
    return InvenTreeClient(base_url=base_url, token=token)


def _read_config(name: str) -> str | None:
    try:
        from django.conf import settings

        value = getattr(settings, name, None)
        if value:
            return value
    except Exception:
        pass
    return os.environ.get(name)
