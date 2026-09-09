import datetime

from app.repositories import fetch_fbs_order_count, fetch_logistics_expenses
from tests.fake_client import FakeClient, FakeQueryResult

DATE_FROM = datetime.date(2026, 8, 1)
DATE_TO = datetime.date(2026, 8, 31)


def test_fetch_logistics_expenses_ozon_has_data_wb_empty():
    client = FakeClient([
        FakeQueryResult([], [(5,)]),  # ozon count > 0
        FakeQueryResult([], [(100.0, 10.0, 20.0, 1.0)]),  # ozon sums
        FakeQueryResult([], [(0,)]),  # wb count == 0
    ])

    result = fetch_logistics_expenses(client, DATE_FROM, DATE_TO)

    assert result.date_from == DATE_FROM
    assert result.date_to == DATE_TO
    assert result.ozon.logistics_cost == 100.0
    assert result.ozon.returned_logistics_cost == 10.0
    assert result.ozon.last_mile_cost == 20.0
    assert result.ozon.cancel_last_mile_cost == 1.0
    assert result.ozon.total == 131.0
    assert result.wb is None


def test_fetch_logistics_expenses_ozon_empty_period():
    client = FakeClient([
        FakeQueryResult([], [(0,)]),  # ozon count == 0
        FakeQueryResult([], [(0,)]),  # wb count == 0
    ])

    result = fetch_logistics_expenses(client, DATE_FROM, DATE_TO)

    assert result.ozon is None
    assert result.wb is None


def test_fetch_logistics_expenses_wb_has_data():
    client = FakeClient([
        FakeQueryResult([], [(0,)]),  # ozon count == 0
        FakeQueryResult([], [(3,)]),  # wb count > 0
        FakeQueryResult([], [(50.0, 5.0)]),  # wb sums
    ])

    result = fetch_logistics_expenses(client, DATE_FROM, DATE_TO)

    assert result.ozon is None
    assert result.wb.logistics_cost == 50.0
    assert result.wb.reverse_logistics_cost == 5.0
    assert result.wb.total == 55.0


def test_fetch_logistics_expenses_id_client_filters_ozon_only():
    client = FakeClient([
        FakeQueryResult([], [(0,)]),
        FakeQueryResult([], [(0,)]),
    ])

    fetch_logistics_expenses(client, DATE_FROM, DATE_TO, id_client=1)

    assert "id_client = {id_client:UInt8}" in client.queries[0]
    assert client.query_params[0]["id_client"] == 1
    # wildberies.logistics_costs has no id_client column
    assert "id_client" not in client.queries[1]
    assert "id_client" not in client.query_params[1]


def test_fetch_logistics_expenses_queries_correct_tables():
    client = FakeClient([
        FakeQueryResult([], [(0,)]),
        FakeQueryResult([], [(0,)]),
    ])

    fetch_logistics_expenses(client, DATE_FROM, DATE_TO)

    assert "ozon.expenses_agg" in client.queries[0]
    assert "wildberies.logistics_costs" in client.queries[1]


def test_fetch_fbs_order_count_maps_both_marketplaces():
    client = FakeClient([
        FakeQueryResult([], [(12,)]),  # ozon count
        FakeQueryResult([], [(7,)]),   # wb count
    ])

    result = fetch_fbs_order_count(client, DATE_FROM, DATE_TO)

    assert result.date_from == DATE_FROM
    assert result.date_to == DATE_TO
    assert result.ozon == 12
    assert result.wb == 7
    assert "ozon.ozon_fbs_postings" in client.queries[0]
    assert "wildberies.orders" in client.queries[1]
    assert "fbs = true" in client.queries[1]


def test_fetch_fbs_order_count_id_client_filters_both():
    client = FakeClient([
        FakeQueryResult([], [(0,)]),
        FakeQueryResult([], [(0,)]),
    ])

    fetch_fbs_order_count(client, DATE_FROM, DATE_TO, id_client=1)

    assert client.query_params[0]["id_client"] == 1
    assert client.query_params[1]["id_client"] == 1
