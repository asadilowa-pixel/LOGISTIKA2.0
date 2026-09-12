from fastapi.testclient import TestClient

from app.dependencies import get_ch_client
from app.main import app
from tests.fake_client import FakeClient, FakeQueryResult


def _authed_client(fake: FakeClient, basic_auth_headers: dict[str, str]) -> TestClient:
    app.dependency_overrides[get_ch_client] = lambda: fake
    return TestClient(app, headers=basic_auth_headers)


def test_expenses_logistics_endpoint_returns_ozon_and_null_wb(basic_auth_headers):
    fake = FakeClient([
        FakeQueryResult([], [(5,)]),
        FakeQueryResult([], [(100.0, 10.0, 20.0, 1.0)]),
        FakeQueryResult([], [(0,)]),
    ])
    client = _authed_client(fake, basic_auth_headers)

    resp = client.get(
        "/expenses/logistics", params={"date_from": "2026-08-01", "date_to": "2026-08-31"}
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["ozon"]["total"] == 131.0
    assert body["wb"] is None


def test_expenses_logistics_rejects_inverted_date_range(basic_auth_headers):
    client = _authed_client(FakeClient([]), basic_auth_headers)

    resp = client.get(
        "/expenses/logistics", params={"date_from": "2026-08-31", "date_to": "2026-08-01"}
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_expenses_logistics_requires_date_params(basic_auth_headers):
    client = _authed_client(FakeClient([]), basic_auth_headers)

    resp = client.get("/expenses/logistics")

    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_orders_fbs_count_endpoint(basic_auth_headers):
    fake = FakeClient([
        FakeQueryResult([], [(12,)]),
        FakeQueryResult([], [(7,)]),
    ])
    client = _authed_client(fake, basic_auth_headers)

    resp = client.get(
        "/orders/fbs-count", params={"date_from": "2026-08-01", "date_to": "2026-08-31"}
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["ozon"] == 12
    assert body["wb"] == 7


def test_orders_fbs_count_rejects_inverted_date_range(basic_auth_headers):
    client = _authed_client(FakeClient([]), basic_auth_headers)

    resp = client.get(
        "/orders/fbs-count", params={"date_from": "2026-08-31", "date_to": "2026-08-01"}
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_expenses_logistics_requires_auth():
    fake = FakeClient([])
    app.dependency_overrides[get_ch_client] = lambda: fake
    client = TestClient(app)

    resp = client.get(
        "/expenses/logistics", params={"date_from": "2026-08-01", "date_to": "2026-08-31"}
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 401
