"""Client HTTP minimal pour l'API REST d'InvenTree."""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urljoin

import requests


class InvenTreeAPIError(Exception):
    """Erreur retournée par l'API InvenTree (status HTTP non-2xx)."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        url: str | None = None,
        payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.payload = payload


class InvenTreeClient:
    """Client HTTP authentifié pour l'API InvenTree."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 10.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url est requis")
        if not token:
            raise ValueError("token est requis")

        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update({
            "Authorization": f"Token {token}",
            "Accept": "application/json",
        })

    # ------------------------------------------------------------------
    # Parts
    # ------------------------------------------------------------------

    def list_parts(
        self,
        *,
        category: int | None = None,
        search: str | None = None,
        **filters: Any,
    ) -> Any:
        """GET `/api/part/` — liste les pièces (paginé par InvenTree)."""
        params: dict[str, Any] = dict(filters)
        if category is not None:
            params["category"] = category
        if search is not None:
            params["search"] = search
        return self._request("GET", "api/part/", params=params)

    def get_part(self, pk: int) -> Any:
        """GET `/api/part/{pk}/` — détail d'une pièce."""
        return self._request("GET", f"api/part/{pk}/")

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    def list_categories(
        self,
        *,
        parent: int | None = None,
        **filters: Any,
    ) -> Any:
        """GET `/api/part/category/` — liste les catégories de pièces."""
        params: dict[str, Any] = dict(filters)
        if parent is not None:
            params["parent"] = parent
        return self._request("GET", "api/part/category/", params=params)

    def get_category(self, pk: int) -> Any:
        """GET `/api/part/category/{pk}/` — détail d'une catégorie."""
        return self._request("GET", f"api/part/category/{pk}/")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "InvenTreeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        url = urljoin(self.base_url, path.lstrip("/"))
        try:
            response = self._session.request(
                method,
                url,
                params=params,
                json=json,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise InvenTreeAPIError(
                f"Échec de la requête {method} {url}: {exc}",
                url=url,
            ) from exc

        if not response.ok:
            raise InvenTreeAPIError(
                f"{method} {url} a retourné {response.status_code}",
                status_code=response.status_code,
                url=url,
                payload=_safe_json(response),
            )

        if not response.content:
            return None
        return response.json()


def _safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text
