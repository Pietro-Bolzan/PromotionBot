"""Who can reach what.

The promotion routes spend money (OpenAI) and expose the catalog, so every one
of them must refuse a request without the right X-API-KEY.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

PROMOTION_ID = uuid.uuid4()
PROTECTED_ROUTES = [
    ("POST", "/api/promotions/run"),
    ("POST", f"/api/promotions/{PROMOTION_ID}/generate-copy"),
    ("GET", "/api/promotions"),
    ("POST", f"/api/promotions/{PROMOTION_ID}/send-telegram"),
    ("POST", "/api/promotions/send-pending-telegram"),
]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(("method", "path"), PROTECTED_ROUTES)
def test_protected_route_refuses_a_request_without_key(client, method, path):
    response = client.request(method, path)

    assert response.status_code == 401
    assert response.json() == {"detail": "Missing API key"}


@pytest.mark.parametrize(("method", "path"), PROTECTED_ROUTES)
def test_protected_route_refuses_a_wrong_key(client, method, path):
    response = client.request(method, path, headers={"X-API-KEY": "wrong"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}


def test_non_ascii_key_is_refused_not_a_server_error(client):
    # Regression: compare_digest raised TypeError on non-ASCII str, turning a
    # bad key into a 500. Sent as raw bytes, as any HTTP client can.
    response = client.get(
        "/api/promotions", headers={"X-API-KEY": "chaveç".encode("latin-1")}
    )

    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/", "/health"])
def test_public_routes_need_no_key(client, path):
    assert client.get(path).status_code == 200


def test_openapi_documents_the_key_on_every_protected_route():
    paths = app.openapi()["paths"]

    protected = {path for path, operations in paths.items() if path.startswith("/api/")}
    for path in protected:
        for operation in paths[path].values():
            assert operation.get("security") == [{"APIKeyHeader": []}], path
