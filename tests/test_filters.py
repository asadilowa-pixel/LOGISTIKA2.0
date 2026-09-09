"""Covers the id_client / marketplace query filters added to repositories
and routers. Uses the same FakeClient/FakeQueryResult as the other test
modules; see those for the full per-table column layouts."""

import base64

from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import get_ch_client
from app.main import app
from app.repositories import (
    fetch_mysklad_supplies_marketplaces,
    fetch_ozon_stocks_fbo,
    fetch_unified_stocks,
)
from tests.fake_client import FakeClient, FakeQueryResult


def _basic_auth_headers() -> dict[str, str]:
    """Installed starlette's TestClient has no `auth=` constructor kwarg, so
    build the Basic Authorization header directly instead."""
    credentials = base64.b64encode(
        f"{settings.dashboard_user}:{settings.dashboard_password}".encode()
    ).decode()
    return {"Authorization": f"Basic {credentials}"}

OZON_FBO_COLUMNS = [
    "sku", "article_seller", "name_goods", "stocks", "on_way", "reserv",
    "sklad_name", "name_cabinet", "id_cabinet", "id_client", "update_at",
]


def test_fetch_ozon_stocks_fbo_no_filter_omits_where_clause():
    client = FakeClient(FakeQueryResult(OZON_FBO_COLUMNS, []))

    fetch_ozon_stocks_fbo(client)

    assert "WHERE" not in client.queries[0]
    assert client.query_params[0] == {}


def test_fetch_ozon_stocks_fbo_filters_by_id_client():
    client = FakeClient(FakeQueryResult(OZON_FBO_COLUMNS, []))

    fetch_ozon_stocks_fbo(client, id_client=1)

    assert "WHERE id_client = {id_client:UInt8}" in client.queries[0]
    assert client.query_params[0] == {"id_client": 1}


def test_fetch_unified_stocks_marketplace_wb_only_queries_wb_tables():
    client = FakeClient({
        "wildberies.stocks_fbo": FakeQueryResult(
            ["sklad", "article_seller", "article", "barcode", "stocks_current_day",
             "to_customer", "from_customer", "stocks_current_day_full", "category",
             "subject", "brand", "tech_size", "price", "discount", "name_cabinet",
             "id_client", "id_cabinet"],
            [],
        ),
        "wildberies.stocks_fbs": FakeQueryResult(
            ["article", "article_seller", "stocks", "sklad", "barcode", "subject",
             "brand", "cabinet_name", "id_client", "id_cabinet", "photo", "ssilka",
             "sebes", "tag", "tag_obj"],
            [],
        ),
    })

    fetch_unified_stocks(client, marketplace="wb")

    assert all("ozon" not in q for q in client.queries)
    assert any("wildberies.stocks_fbo" in q for q in client.queries)
    assert any("wildberies.stocks_fbs" in q for q in client.queries)


def test_fetch_mysklad_supplies_marketplaces_filters_by_both():
    columns = [
        "supply_id", "supply_name", "moment", "marketplace", "supply_sum",
        "position_id", "quantity", "price", "product_id", "article",
        "product_name", "path_name", "name_cabinet", "id_cabinet",
        "id_client", "update_at",
    ]
    client = FakeClient(FakeQueryResult(columns, []))

    fetch_mysklad_supplies_marketplaces(client, id_client=1, marketplace="wb")

    query = client.queries[0]
    assert "id_client = {id_client:UInt8}" in query
    assert "marketplace = {marketplace:String}" in query
    assert client.query_params[0] == {"id_client": 1, "marketplace": "wb"}


def test_unified_endpoint_rejects_invalid_marketplace():
    app.dependency_overrides[get_ch_client] = lambda: FakeClient(FakeQueryResult([], []))
    client = TestClient(app, headers=_basic_auth_headers())

    resp = client.get("/stocks/unified", params={"marketplace": "aliexpress"})

    app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_unified_endpoint_accepts_valid_marketplace():
    columns = [
        "sklad", "article_seller", "article", "barcode", "stocks_current_day",
        "to_customer", "from_customer", "stocks_current_day_full", "category",
        "subject", "brand", "tech_size", "price", "discount", "name_cabinet",
        "id_client", "id_cabinet",
    ]
    fbs_columns = [
        "article", "article_seller", "stocks", "sklad", "barcode", "subject",
        "brand", "cabinet_name", "id_client", "id_cabinet", "photo", "ssilka",
        "sebes", "tag", "tag_obj",
    ]
    fake = FakeClient({
        "wildberies.stocks_fbo": FakeQueryResult(columns, []),
        "wildberies.stocks_fbs": FakeQueryResult(fbs_columns, []),
    })
    app.dependency_overrides[get_ch_client] = lambda: fake
    client = TestClient(app, headers=_basic_auth_headers())

    resp = client.get("/stocks/unified", params={"marketplace": "wb"})

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == []
