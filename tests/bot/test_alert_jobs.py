import datetime

from app.bot import state
from app.bot.alert_jobs import check_fbs_deadlines


def test_check_fbs_deadlines_alerts_once_per_order():
    conn = state.connect(":memory:")
    now = datetime.datetime.fromisoformat("2026-09-13T06:00:00+00:00")
    deadlines = {"P-1": datetime.datetime.fromisoformat("2026-09-13T08:00:00+00:00")}

    first_run = check_fbs_deadlines(
        conn, marketplace="ozon", cabinet_id=1, deadlines=deadlines, now=now, threshold_hours=4.0
    )
    second_run = check_fbs_deadlines(
        conn, marketplace="ozon", cabinet_id=1, deadlines=deadlines, now=now, threshold_hours=4.0
    )

    assert len(first_run) == 1
    assert "P-1" in first_run[0]
    assert second_run == []


def test_check_fbs_deadlines_ignores_orders_outside_threshold():
    conn = state.connect(":memory:")
    now = datetime.datetime.fromisoformat("2026-09-13T06:00:00+00:00")
    deadlines = {"P-1": datetime.datetime.fromisoformat("2026-09-14T06:00:00+00:00")}

    alerts = check_fbs_deadlines(
        conn, marketplace="ozon", cabinet_id=1, deadlines=deadlines, now=now, threshold_hours=4.0
    )

    assert alerts == []
