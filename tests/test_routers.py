import datetime

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_ch_client
from app.main import app
from tests.fake_client import FakeClient, FakeQueryResult

UPDATE_AT = datetime.datetime(2026, 9, 9, 12, 0, 0)


@pytest.fixture()
def client_with(request):
    """Builds a TestClient with get_ch_client overridden to return a FakeClient
    backed by the given FakeQueryResult. TestClient is instantiated without the
    `with` context manager so the app's real-ClickHouse lifespan never runs."""

    def _make(result: FakeQueryResult) -> TestClient:
        fake = FakeClient(result)
        app.dependency_overrides[get_ch_client] = lambda: fake
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def test_ozon_fbo_endpoint(client_with):
    columns = [
        "sku", "article_seller", "name_goods", "stocks", "on_way", "reserv",
        "sklad_name", "name_cabinet", "id_cabinet", "id_client", "update_at",
    ]
    row = (1, "A1", "Товар", 5, 0, 1, "Склад", "Кабинет", 1, 1, UPDATE_AT)
    client = client_with(FakeQueryResult(columns, [row]))

    resp = client.get("/stocks/ozon/fbo")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["sku"] == 1
    assert body[0]["article_seller"] == "A1"


def test_ozon_fbs_endpoint(client_with):
    columns = [
        "sku", "article_seller", "stocks", "reserv", "warehouse_id",
        "sklad_name", "name_cabinet", "id_cabinet", "id_client", "update_at",
    ]
    row = (2, "A2", 3, 0, 100, "Склад", "Кабинет", 1, 1, UPDATE_AT)
    client = client_with(FakeQueryResult(columns, [row]))

    resp = client.get("/stocks/ozon/fbs")

    assert resp.status_code == 200
    assert resp.json()[0]["warehouse_id"] == 100


def test_wb_fbo_endpoint(client_with):
    columns = [
        "sklad", "article_seller", "article", "barcode", "stocks_current_day",
        "to_customer", "from_customer", "stocks_current_day_full", "category",
        "subject", "brand", "tech_size", "price", "discount", "name_cabinet",
        "id_client", "id_cabinet",
    ]
    row = (
        "Склад", "A3", 3, "barcode", 1, 0, 1, 1, "Категория", "Предмет",
        "Бренд", "0", 100.0, 10.0, "Кабинет", 1, 1,
    )
    client = client_with(FakeQueryResult(columns, [row]))

    resp = client.get("/stocks/wb/fbo")

    assert resp.status_code == 200
    assert resp.json()[0]["article"] == 3


def test_wb_fbs_endpoint_empty(client_with):
    columns = [
        "article", "article_seller", "stocks", "sklad", "barcode", "subject",
        "brand", "cabinet_name", "id_client", "id_cabinet", "photo", "ssilka",
        "sebes", "tag", "tag_obj",
    ]
    client = client_with(FakeQueryResult(columns, []))

    resp = client.get("/stocks/wb/fbs")

    assert resp.status_code == 200
    assert resp.json() == []


def test_unified_stocks_endpoint(client_with):
    ozon_fbo_columns = [
        "sku", "article_seller", "name_goods", "stocks", "on_way", "reserv",
        "sklad_name", "name_cabinet", "id_cabinet", "id_client", "update_at",
    ]
    ozon_fbo_row = (1, "OZ-FBO", "Товар", 5, 0, 1, "Склад", "Кабинет", 1, 1, UPDATE_AT)

    ozon_fbs_columns = [
        "sku", "article_seller", "stocks", "reserv", "warehouse_id",
        "sklad_name", "name_cabinet", "id_cabinet", "id_client", "update_at",
    ]
    ozon_fbs_row = (2, "OZ-FBS", 3, 0, 100, "Склад", "Кабинет", 1, 1, UPDATE_AT)

    wb_fbo_columns = [
        "sklad", "article_seller", "article", "barcode", "stocks_current_day",
        "to_customer", "from_customer", "stocks_current_day_full", "category",
        "subject", "brand", "tech_size", "price", "discount", "name_cabinet",
        "id_client", "id_cabinet",
    ]
    wb_fbo_row = (
        "Склад", "WB-FBO", 3, "barcode", 4, 0, 1, 1, "Категория", "Предмет",
        "Бренд", "0", 100.0, 10.0, "Кабинет", 1, 1,
    )

    wb_fbs_columns = [
        "article", "article_seller", "stocks", "sklad", "barcode", "subject",
        "brand", "cabinet_name", "id_client", "id_cabinet", "photo", "ssilka",
        "sebes", "tag", "tag_obj",
    ]
    wb_fbs_row = (
        "WB-FBS", "WB-FBS", 7, "Склад", "barcode", "Предмет", "Бренд",
        "Кабинет", 1, 1, "photo_url", "link", 50.0, "tag", "tag_obj",
    )

    client = client_with({
        "ozon.stocks_fbo": FakeQueryResult(ozon_fbo_columns, [ozon_fbo_row]),
        "ozon.stocks_fbs": FakeQueryResult(ozon_fbs_columns, [ozon_fbs_row]),
        "wildberies.stocks_fbo": FakeQueryResult(wb_fbo_columns, [wb_fbo_row]),
        "wildberies.stocks_fbs": FakeQueryResult(wb_fbs_columns, [wb_fbs_row]),
    })

    resp = client.get("/stocks/unified")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 4
    marketplaces = {(item["marketplace"], item["fulfillment"]) for item in body}
    assert marketplaces == {("ozon", "fbo"), ("ozon", "fbs"), ("wb", "fbo"), ("wb", "fbs")}


def test_mysklad_orders_supplies_endpoint(client_with):
    columns = [
        "supply_id", "updated", "name", "description", "moment", "created",
        "sum", "deliveryPlannedMoment", "agent_name", "position_id",
        "article", "quantity", "price", "name_cabinet", "id_cabinet",
        "id_client", "update_at",
    ]
    row = (
        "sup1", UPDATE_AT, "Поставка 1", "descr", UPDATE_AT, UPDATE_AT,
        1000.0, UPDATE_AT, "Поставщик", "pos1", "A1", 10.0, 100.0,
        "Кабинет", 1, 1, UPDATE_AT,
    )
    client = client_with(FakeQueryResult(columns, [row]))

    resp = client.get("/mysklad/orders-supplies")

    assert resp.status_code == 200
    assert resp.json()[0]["supply_id"] == "sup1"


def test_mysklad_supplies_marketplaces_endpoint(client_with):
    columns = [
        "supply_id", "supply_name", "moment", "marketplace", "supply_sum",
        "position_id", "quantity", "price", "product_id", "article",
        "product_name", "path_name", "name_cabinet", "id_cabinet",
        "id_client", "update_at",
    ]
    row = (
        "sup2", "Поставка 2", UPDATE_AT, "ozon", 500.0, "pos2", 5, 100.0,
        "prod1", "A2", "Товар", "путь", "Кабинет", 1, 1, UPDATE_AT,
    )
    client = client_with(FakeQueryResult(columns, [row]))

    resp = client.get("/mysklad/supplies-marketplaces")

    assert resp.status_code == 200
    assert resp.json()[0]["marketplace"] == "ozon"


def test_watchdog_freshness_endpoint(client_with):
    columns = [
        "run_id", "checked_at", "spreadsheet_id", "spreadsheet_name",
        "sheet_name", "filled_by", "date_column", "last_date", "lag_days",
        "allowed_days", "verdict", "detail",
    ]
    row = (
        "run1", UPDATE_AT, "sheet_id", "sheet_name", "tab", "someone", "A",
        datetime.date(2026, 9, 8), 1, 7, "ok", "detail text",
    )
    client = client_with(FakeQueryResult(columns, [row]))

    resp = client.get("/watchdog/freshness", params={"limit": 5})

    assert resp.status_code == 200
    assert resp.json()[0]["run_id"] == "run1"


def test_watchdog_runs_endpoint(client_with):
    columns = [
        "run_id", "started_at", "finished_at", "refreshed", "ok", "waiting",
        "deferred", "problems", "fixed", "no_access", "mail_status",
    ]
    row = ("run1", UPDATE_AT, UPDATE_AT, 1, 10, 2, 0, 1, 0, 0, "sent")
    client = client_with(FakeQueryResult(columns, [row]))

    resp = client.get("/watchdog/runs")

    assert resp.status_code == 200
    assert resp.json()[0]["ok"] == 10
