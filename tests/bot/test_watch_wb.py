import json

from app.bot import state
from app.bot.watch_wb import poll_coefficient_watch, start_coefficient_watch


class _FakeWbClient:
    def __init__(self, coefficients):
        self._coefficients = coefficients

    def get_acceptance_coefficients(self, warehouse_ids):
        return self._coefficients


def _make_watch(conn, warehouse_id=507, date_from="2026-09-20", date_to="2026-09-25", max_coefficient=0):
    watch_id = start_coefficient_watch(
        conn, cabinet_id=1, warehouse_id=warehouse_id, date_from=date_from, date_to=date_to,
        max_coefficient=max_coefficient, chat_id=555, now="2026-09-13T10:00:00",
    )
    return state.list_watch_requests(conn, status="watching")[0]


def test_start_coefficient_watch_creates_watching_row():
    conn = state.connect(":memory:")

    row = _make_watch(conn)

    assert row["kind"] == "wb_coefficient"
    assert json.loads(row["reference_json"]) == {"warehouse_id": 507}


def test_poll_coefficient_watch_alerts_on_matching_coefficient_in_range():
    conn = state.connect(":memory:")
    row = _make_watch(conn)
    wb = _FakeWbClient([{"warehouseID": 507, "date": "2026-09-21T00:00:00Z", "coefficient": 0}])

    message = poll_coefficient_watch(wb, conn, row, now="2026-09-13T10:05:00", cooldown_minutes=60)

    assert message is not None
    assert "507" in message


def test_poll_coefficient_watch_ignores_coefficient_above_max():
    conn = state.connect(":memory:")
    row = _make_watch(conn, max_coefficient=0)
    wb = _FakeWbClient([{"warehouseID": 507, "date": "2026-09-21T00:00:00Z", "coefficient": 1}])

    message = poll_coefficient_watch(wb, conn, row, now="2026-09-13T10:05:00", cooldown_minutes=60)

    assert message is None


def test_poll_coefficient_watch_ignores_dates_outside_range():
    conn = state.connect(":memory:")
    row = _make_watch(conn, date_from="2026-09-20", date_to="2026-09-25")
    wb = _FakeWbClient([{"warehouseID": 507, "date": "2026-10-01T00:00:00Z", "coefficient": 0}])

    message = poll_coefficient_watch(wb, conn, row, now="2026-09-13T10:05:00", cooldown_minutes=60)

    assert message is None


def test_poll_coefficient_watch_does_not_repeat_within_cooldown():
    conn = state.connect(":memory:")
    row = _make_watch(conn)
    wb = _FakeWbClient([{"warehouseID": 507, "date": "2026-09-21T00:00:00Z", "coefficient": 0}])

    first = poll_coefficient_watch(wb, conn, row, now="2026-09-13T10:05:00", cooldown_minutes=60)
    second = poll_coefficient_watch(wb, conn, row, now="2026-09-13T10:06:00", cooldown_minutes=60)

    assert first is not None
    assert second is None


def test_poll_coefficient_watch_repeats_after_cooldown_expires():
    conn = state.connect(":memory:")
    row = _make_watch(conn)
    wb = _FakeWbClient([{"warehouseID": 507, "date": "2026-09-21T00:00:00Z", "coefficient": 0}])

    first = poll_coefficient_watch(wb, conn, row, now="2026-09-13T10:00:00", cooldown_minutes=60)
    second = poll_coefficient_watch(wb, conn, row, now="2026-09-13T11:30:00", cooldown_minutes=60)

    assert first is not None
    assert second is not None
