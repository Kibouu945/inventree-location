"""Tests du client HTTP InvenTree (mocks via la lib `responses`)."""

from __future__ import annotations

import pytest
import responses

from inventree_location.clients import InvenTreeAPIError, InvenTreeClient


BASE_URL = "http://inventree.test"
TOKEN = "secret-token-123"


@pytest.fixture
def client():
    c = InvenTreeClient(base_url=BASE_URL, token=TOKEN)
    yield c
    c.close()


class TestInit:
    def test_requires_base_url(self):
        with pytest.raises(ValueError):
            InvenTreeClient(base_url="", token=TOKEN)

    def test_requires_token(self):
        with pytest.raises(ValueError):
            InvenTreeClient(base_url=BASE_URL, token="")

    def test_normalizes_trailing_slash(self):
        c = InvenTreeClient(base_url="http://x.test", token=TOKEN)
        assert c.base_url == "http://x.test/"
        c2 = InvenTreeClient(base_url="http://x.test/", token=TOKEN)
        assert c2.base_url == "http://x.test/"


class TestAuthHeader:
    @responses.activate
    def test_sends_token_header(self, client):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/part/",
            json={"results": []},
            status=200,
        )
        client.list_parts()
        call = responses.calls[0]
        assert call.request.headers["Authorization"] == f"Token {TOKEN}"
        assert call.request.headers["Accept"] == "application/json"


class TestListParts:
    @responses.activate
    def test_without_filters(self, client):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/part/",
            json={"count": 0, "results": []},
            status=200,
        )
        result = client.list_parts()
        assert result == {"count": 0, "results": []}

    @responses.activate
    def test_with_category_and_extra_filters(self, client):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/part/",
            json={"results": [{"pk": 1}]},
            status=200,
        )
        client.list_parts(category=3, active=True, search="cable")
        params = responses.calls[0].request.params
        assert params["category"] == "3"
        assert params["active"] == "True"
        assert params["search"] == "cable"


class TestGetPart:
    @responses.activate
    def test_get_part(self, client):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/part/42/",
            json={"pk": 42, "name": "Tente"},
            status=200,
        )
        assert client.get_part(42) == {"pk": 42, "name": "Tente"}


class TestCategories:
    @responses.activate
    def test_list_categories(self, client):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/part/category/",
            json={"results": [{"pk": 1, "name": "Camping"}]},
            status=200,
        )
        client.list_categories(parent=5)
        assert responses.calls[0].request.params["parent"] == "5"

    @responses.activate
    def test_get_category(self, client):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/part/category/7/",
            json={"pk": 7, "name": "Tentes"},
            status=200,
        )
        assert client.get_category(7) == {"pk": 7, "name": "Tentes"}


class TestErrors:
    @responses.activate
    def test_404_raises_api_error(self, client):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/part/999/",
            json={"detail": "Not found."},
            status=404,
        )
        with pytest.raises(InvenTreeAPIError) as excinfo:
            client.get_part(999)
        assert excinfo.value.status_code == 404
        assert excinfo.value.payload == {"detail": "Not found."}

    @responses.activate
    def test_500_raises_api_error(self, client):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/part/",
            body="boom",
            status=500,
        )
        with pytest.raises(InvenTreeAPIError) as excinfo:
            client.list_parts()
        assert excinfo.value.status_code == 500
        assert excinfo.value.payload == "boom"

    @responses.activate
    def test_connection_error_raises_api_error(self, client):
        import requests as _requests

        responses.add(
            responses.GET,
            f"{BASE_URL}/api/part/",
            body=_requests.exceptions.ConnectionError("offline"),
        )
        with pytest.raises(InvenTreeAPIError) as excinfo:
            client.list_parts()
        assert excinfo.value.status_code is None


class TestContextManager:
    def test_close_is_idempotent(self):
        c = InvenTreeClient(base_url=BASE_URL, token=TOKEN)
        c.close()
        c.close()

    def test_context_manager_closes(self):
        with InvenTreeClient(base_url=BASE_URL, token=TOKEN) as c:
            assert c.base_url.startswith(BASE_URL)
