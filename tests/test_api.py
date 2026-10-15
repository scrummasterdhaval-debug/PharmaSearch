import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_healthz_is_ok(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_readyz_reports_the_loaded_corpus(client):
    body = client.get("/readyz").json()
    assert body["status"] == "ready"
    assert body["documents"] > 0


def test_search_returns_scored_results(client):
    body = client.get("/search", params={"q": "data integrity audit trail"}).json()
    assert body["total"] > 0
    assert body["results"][0]["score"] > 0
    assert body["results"][0]["citation"]
    # Scores must arrive sorted; clients page on this order.
    scores = [r["score"] for r in body["results"]]
    assert scores == sorted(scores, reverse=True)


def test_search_filters_by_jurisdiction(client):
    body = client.get("/search", params={"q": "quality", "jurisdiction": "ICH"}).json()
    assert {r["jurisdiction"] for r in body["results"]} == {"ICH"}


def test_blank_query_is_rejected(client):
    assert client.get("/search", params={"q": ""}).status_code == 422


def test_limit_above_the_cap_is_rejected(client):
    """An unbounded limit is a cheap way to make a cloud service fall over."""
    assert client.get("/search", params={"q": "gmp", "limit": 10_000}).status_code == 422


def test_every_response_carries_a_request_id(client):
    response = client.get("/healthz")
    assert response.headers["x-request-id"]


def test_incoming_request_id_is_echoed(client):
    response = client.get("/healthz", headers={"x-request-id": "trace-abc"})
    assert response.headers["x-request-id"] == "trace-abc"
