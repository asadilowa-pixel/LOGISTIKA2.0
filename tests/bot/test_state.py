from app.bot import state


def test_create_and_list_watch_requests():
    conn = state.connect(":memory:")

    watch_id = state.create_watch_request(
        conn,
        marketplace="ozon",
        cabinet_id=1,
        kind="ozon_draft_create",
        reference_json='{"draft_id": "abc"}',
        date_from="2026-09-20",
        date_to="2026-09-25",
        max_coefficient=0,
        requested_by_chat_id=999,
        now="2026-09-13T10:00:00",
    )

    rows = state.list_watch_requests(conn, status="watching")

    assert len(rows) == 1
    assert rows[0]["id"] == watch_id
    assert rows[0]["marketplace"] == "ozon"
    assert rows[0]["status"] == "watching"


def test_update_watch_status_moves_out_of_listing():
    conn = state.connect(":memory:")
    watch_id = state.create_watch_request(
        conn,
        marketplace="wb",
        cabinet_id=2,
        kind="wb_coefficient",
        reference_json="{}",
        date_from="2026-09-20",
        date_to="2026-09-25",
        max_coefficient=0,
        requested_by_chat_id=999,
        now="2026-09-13T10:00:00",
    )

    state.update_watch_status(conn, watch_id, "booked", "2026-09-13T11:00:00")

    assert state.list_watch_requests(conn, status="watching") == []
    assert state.list_watch_requests(conn, status="booked")[0]["id"] == watch_id


def test_record_alert_dedups():
    conn = state.connect(":memory:")

    first = state.record_alert(
        conn, marketplace="ozon", cabinet_id=1, order_key="P-1", alert_type="deadline_risk",
        now="2026-09-13T10:00:00",
    )
    second = state.record_alert(
        conn, marketplace="ozon", cabinet_id=1, order_key="P-1", alert_type="deadline_risk",
        now="2026-09-13T10:05:00",
    )

    assert first is True
    assert second is False
