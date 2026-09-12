import datetime

from app.bot.fbs_status import (
    FbsSnapshot,
    format_status_message,
    orders_at_risk,
    ozon_order_deadlines,
    summarize,
    wb_order_deadlines,
)


def test_ozon_order_deadlines_extracts_shipment_date():
    postings = [
        {"posting_number": "P-1", "shipment_date": "2026-09-14T10:00:00+00:00"},
        {"posting_number": "P-2", "shipment_date": None},
    ]

    deadlines = ozon_order_deadlines(postings)

    assert deadlines == {"P-1": datetime.datetime.fromisoformat("2026-09-14T10:00:00+00:00")}


def test_wb_order_deadlines_adds_assembly_hours_to_created_at():
    orders = [{"orderUid": "O-1", "createdAt": "2026-09-13T00:00:00+00:00"}]

    deadlines = wb_order_deadlines(orders, assembly_hours=48.0)

    assert deadlines == {"O-1": datetime.datetime.fromisoformat("2026-09-15T00:00:00+00:00")}


def test_summarize_picks_earliest_deadline():
    deadlines = {
        "P-1": datetime.datetime.fromisoformat("2026-09-14T10:00:00+00:00"),
        "P-2": datetime.datetime.fromisoformat("2026-09-13T08:00:00+00:00"),
    }

    snapshot = summarize("ozon", cabinet_id=1, deadlines=deadlines, pending_count=2)

    assert snapshot == FbsSnapshot(
        marketplace="ozon", cabinet_id=1, pending_count=2,
        earliest_deadline=datetime.datetime.fromisoformat("2026-09-13T08:00:00+00:00"),
    )


def test_format_status_message_lists_each_snapshot():
    now = datetime.datetime.fromisoformat("2026-09-13T06:00:00+00:00")
    snapshots = [
        FbsSnapshot("ozon", 1, 3, datetime.datetime.fromisoformat("2026-09-13T10:00:00+00:00")),
        FbsSnapshot("wb", 2, 0, None),
    ]

    message = format_status_message(snapshots, now)

    assert "ozon (кабинет 1): к отгрузке 3, ближайший дедлайн через 4.0 ч" in message
    assert "wb (кабинет 2): нет заказов к отгрузке" in message


def test_orders_at_risk_filters_by_threshold():
    now = datetime.datetime.fromisoformat("2026-09-13T06:00:00+00:00")
    deadlines = {
        "P-1": datetime.datetime.fromisoformat("2026-09-13T08:00:00+00:00"),
        "P-2": datetime.datetime.fromisoformat("2026-09-14T06:00:00+00:00"),
    }

    at_risk = orders_at_risk(deadlines, now, threshold_hours=4.0)

    assert at_risk == {"P-1": deadlines["P-1"]}
