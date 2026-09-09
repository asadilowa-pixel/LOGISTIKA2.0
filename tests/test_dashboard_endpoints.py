import base64

from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import get_ch_client
from app.main import app
from tests.fake_client import FakeClient, FakeQueryResult


def _basic_auth_headers() -> dict[str, str]:
    """Installed starlette's TestClient has no `auth=` constructor kwarg, so
    build the Basic Authorization header directly instead."""
    credentials = base64.b64encode(
        f"{settings.dashboard_user}:{settings.dashboard_password}".encode()
    ).decode()
    return {"Authorization": f"Basic {credentials}"}


def _authed_client(fake: FakeClient) -> TestClient:
    app.dependency_overrides[get_ch_client] = lambda: fake
    return TestClient(app, headers=_basic_auth_headers())


def test_expenses_logistics_endpoint_returns_ozon_and_null_wb():
    fake = FakeClient([
        FakeQueryResult([], [(5,)]),
        FakeQueryResult([], [(100.0, 10.0, 20.0, 1.0)]),
        FakeQueryResult([], [(0,)]),
    ])
    client = _authed_client(fake)

    resp = client.get(
        "/expenses/logistics", params={"date_from": "2026-08-01", "date_to": "2026-08-31"}
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["ozon"]["total"] == 131.0
    assert body["wb"] is None


def test_expenses_logistics_rejects_inverted_date_range():
    client = _authed_client(FakeClient([]))

    resp = client.get(
        "/expenses/logistics", params={"date_from": "2026-08-31", "date_to": "2026-08-01"}
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_expenses_logistics_requires_date_params():
    client = _authed_client(FakeClient([]))

    resp = client.get("/expenses/logistics")

    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_orders_fbs_count_endpoint():
    fake = FakeClient([
        FakeQueryResult([], [(12,)]),
        FakeQueryResult([], [(7,)]),
    ])
    client = _authed_client(fake)

    resp = client.get(
        "/orders/fbs-count", params={"date_from": "2026-08-01", "date_to": "2026-08-31"}
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["ozon"] == 12
    assert body["wb"] == 7


def test_orders_fbs_count_rejects_inverted_date_range():
    client = _authed_client(FakeClient([]))

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
