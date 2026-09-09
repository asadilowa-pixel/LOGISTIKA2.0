import datetime

from app.repositories import (
    fetch_ozon_stocks_fbo,
    fetch_ozon_stocks_fbs,
    fetch_watchdog_freshness,
    fetch_watchdog_runs,
    fetch_wb_stocks_fbo,
    fetch_wb_stocks_fbs,
)
from tests.fake_client import FakeClient, FakeQueryResult

UPDATE_AT = datetime.datetime(2026, 9, 9, 12, 0, 0)


def test_fetch_ozon_stocks_fbo_maps_rows_and_queries_correct_table():
    columns = [
        "sku", "article_seller", "name_goods", "stocks", "on_way", "reserv",
        "sklad_name", "name_cabinet", "id_cabinet", "id_client", "update_at",
    ]
    row = (1, "A1", "Товар", 5, 0, 1, "Склад", "Кабинет", 1, 1, UPDATE_AT)
    client = FakeClient(FakeQueryResult(columns, [row]))

    result = fetch_ozon_stocks_fbo(client)

    assert len(result) == 1
    assert result[0].sku == 1
    assert result[0].article_seller == "A1"
    assert result[0].update_at == UPDATE_AT
    assert "ozon.stocks_fbo" in client.queries[0]


def test_fetch_ozon_stocks_fbs_maps_rows_and_queries_correct_table():
    columns = [
        "sku", "article_seller", "stocks", "reserv", "warehouse_id",
        "sklad_name", "name_cabinet", "id_cabinet", "id_client", "update_at",
    ]
    row = (2, "A2", 3, 0, 100, "Склад", "Кабинет", 1, 1, UPDATE_AT)
    client = FakeClient(FakeQueryResult(columns, [row]))

    result = fetch_ozon_stocks_fbs(client)

    assert len(result) == 1
    assert result[0].warehouse_id == 100
    assert "ozon.stocks_fbs" in client.queries[0]


def test_fetch_wb_stocks_fbo_maps_rows_and_queries_correct_table():
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
    client = FakeClient(FakeQueryResult(columns, [row]))

    result = fetch_wb_stocks_fbo(client)

    assert len(result) == 1
    assert result[0].article == 3
    assert result[0].price == 100.0
    assert "wildberies.stocks_fbo" in client.queries[0]


def test_fetch_wb_stocks_fbs_maps_rows_and_queries_correct_table():
    columns = [
        "article", "article_seller", "stocks", "sklad", "barcode", "subject",
        "brand", "cabinet_name", "id_client", "id_cabinet", "photo", "ssilka",
        "sebes", "tag", "tag_obj",
    ]
    row = (
        "A4", "A4S", 7, "Склад", "barcode", "Предмет", "Бренд", "Кабинет",
        1, 1, "photo_url", "link", 50.0, "tag", "tag_obj",
    )
    client = FakeClient(FakeQueryResult(columns, [row]))

    result = fetch_wb_stocks_fbs(client)

    assert len(result) == 1
    assert result[0].article == "A4"
    assert "wildberies.stocks_fbs" in client.queries[0]


def test_fetch_watchdog_freshness_maps_rows_and_applies_limit():
    columns = [
        "run_id", "checked_at", "spreadsheet_id", "spreadsheet_name",
        "sheet_name", "filled_by", "date_column", "last_date", "lag_days",
        "allowed_days", "verdict", "detail",
    ]
    row = (
        "run1", UPDATE_AT, "sheet_id", "sheet_name", "tab", "someone", "A",
        datetime.date(2026, 9, 8), 1, 7, "ok", "detail text",
    )
    client = FakeClient(FakeQueryResult(columns, [row]))

    result = fetch_watchdog_freshness(client, limit=5)

    assert len(result) == 1
    assert result[0].run_id == "run1"
    assert "watchdog.freshness" in client.queries[0]
    assert "LIMIT 5" in client.queries[0]


def test_fetch_watchdog_runs_maps_rows_and_applies_limit():
    columns = [
        "run_id", "started_at", "finished_at", "refreshed", "ok", "waiting",
        "deferred", "problems", "fixed", "no_access", "mail_status",
    ]
    row = ("run1", UPDATE_AT, UPDATE_AT, 1, 10, 2, 0, 1, 0, 0, "sent")
    client = FakeClient(FakeQueryResult(columns, [row]))

    result = fetch_watchdog_runs(client, limit=10)

    assert len(result) == 1
    assert result[0].ok == 10
    assert "watchdog.runs" in client.queries[0]
    assert "LIMIT 10" in client.queries[0]
