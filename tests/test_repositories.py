import datetime

from app.repositories import (
    fetch_ozon_stocks_fbo,
    fetch_ozon_stocks_fbs,
    fetch_unified_stocks,
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


def test_fetch_unified_stocks_combines_all_four_sources():
    ozon_fbo_columns = [
        "sku", "article_seller", "name_goods", "stocks", "on_way", "reserv",
        "sklad_name", "name_cabinet", "id_cabinet", "id_client", "update_at",
    ]
    ozon_fbo_row = (1, "OZ-FBO", "Товар", 5, 0, 1, "Склад Ozon FBO", "Кабинет", 1, 1, UPDATE_AT)

    ozon_fbs_columns = [
        "sku", "article_seller", "stocks", "reserv", "warehouse_id",
        "sklad_name", "name_cabinet", "id_cabinet", "id_client", "update_at",
    ]
    ozon_fbs_row = (2, "OZ-FBS", 3, 0, 100, "Склад Ozon FBS", "Кабинет", 1, 1, UPDATE_AT)

    wb_fbo_columns = [
        "sklad", "article_seller", "article", "barcode", "stocks_current_day",
        "to_customer", "from_customer", "stocks_current_day_full", "category",
        "subject", "brand", "tech_size", "price", "discount", "name_cabinet",
        "id_client", "id_cabinet",
    ]
    wb_fbo_row = (
        "Склад WB FBO", "WB-FBO", 3, "barcode", None, 0, 1, 1, "Категория",
        "Предмет", "Бренд", "0", 100.0, 10.0, "Кабинет", 1, 1,
    )

    wb_fbs_columns = [
        "article", "article_seller", "stocks", "sklad", "barcode", "subject",
        "brand", "cabinet_name", "id_client", "id_cabinet", "photo", "ssilka",
        "sebes", "tag", "tag_obj",
    ]
    wb_fbs_row = (
        "WB-FBS", "WB-FBS", 7, "Склад WB FBS", "barcode", "Предмет", "Бренд",
        "Кабинет", 1, 1, "photo_url", "link", 50.0, "tag", "tag_obj",
    )

    client = FakeClient({
        "ozon.stocks_fbo": FakeQueryResult(ozon_fbo_columns, [ozon_fbo_row]),
        "ozon.stocks_fbs": FakeQueryResult(ozon_fbs_columns, [ozon_fbs_row]),
        "wildberies.stocks_fbo": FakeQueryResult(wb_fbo_columns, [wb_fbo_row]),
        "wildberies.stocks_fbs": FakeQueryResult(wb_fbs_columns, [wb_fbs_row]),
    })

    result = fetch_unified_stocks(client)

    assert len(result) == 4
    by_key = {(r.marketplace, r.fulfillment): r for r in result}

    ozon_fbo = by_key[("ozon", "fbo")]
    assert ozon_fbo.article_seller == "OZ-FBO"
    assert ozon_fbo.warehouse == "Склад Ozon FBO"
    assert ozon_fbo.quantity == 5

    ozon_fbs = by_key[("ozon", "fbs")]
    assert ozon_fbs.quantity == 3

    wb_fbo = by_key[("wb", "fbo")]
    assert wb_fbo.warehouse == "Склад WB FBO"
    assert wb_fbo.quantity == 0  # stocks_current_day was None -> coerced to 0

    wb_fbs = by_key[("wb", "fbs")]
    assert wb_fbs.warehouse == "Склад WB FBS"
    assert wb_fbs.quantity == 7


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
