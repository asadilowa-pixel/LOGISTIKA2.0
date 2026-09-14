import datetime
import json

from app.bot import state
from app.bot.scheduler import build_scheduler, poll_all_watches, sweep_expired_watches


class _FakeOzonClient:
    def __init__(self, timeslots):
        self._timeslots = timeslots
        self.booked = []

    def get_draft_timeslots(self, draft_id, date_from, date_to):
        return self._timeslots

    def book_draft_timeslot(self, draft_id, timeslot):
        self.booked.append((draft_id, timeslot))


class _FakeWbClient:
    def __init__(self, coefficients):
        self._coefficients = coefficients

    def get_acceptance_coefficients(self, warehouse_ids):
        return self._coefficients


def test_poll_all_watches_dispatches_by_marketplace():
    conn = state.connect(":memory:")
    state.create_watch_request(
        conn, marketplace="ozon", cabinet_id=1, kind="ozon_draft_create",
        reference_json=json.dumps({"draft_id": "draft-1"}), date_from="2026-09-20",
        date_to="2026-09-25", max_coefficient=0, requested_by_chat_id=555,
        now="2026-09-13T10:00:00",
    )
    state.create_watch_request(
        conn, marketplace="wb", cabinet_id=2, kind="wb_coefficient",
        reference_json=json.dumps({"warehouse_id": 507}), date_from="2026-09-20",
        date_to="2026-09-25", max_coefficient=0, requested_by_chat_id=555,
        now="2026-09-13T10:00:00",
    )
    ozon_clients = {1: _FakeOzonClient([{"warehouse_id": 507, "date": "2026-09-20", "coefficient": 0, "timeslot": {}}])}
    wb_clients = {2: _FakeWbClient([{"warehouseID": 507, "date": "2026-09-21T00:00:00Z", "coefficient": 0}])}

    messages = poll_all_watches(
        ozon_clients, wb_clients, conn, now="2026-09-13T10:05:00", cooldown_minutes=60
    )

    assert len(messages) == 2
    remaining = state.list_watch_requests(conn, status="watching")
    assert len(remaining) == 1
    assert remaining[0]["marketplace"] == "wb"


def test_sweep_expired_watches_marks_past_date_to_as_expired():
    conn = state.connect(":memory:")
    watch_id = state.create_watch_request(
        conn, marketplace="ozon", cabinet_id=1, kind="ozon_draft_create",
        reference_json="{}", date_from="2026-09-01", date_to="2026-09-05",
        max_coefficient=0, requested_by_chat_id=555, now="2026-09-01T00:00:00",
    )

    expired = sweep_expired_watches(conn, now="2026-09-13T00:00:00")

    assert expired == [watch_id]
    assert state.list_watch_requests(conn, status="watching") == []


def test_sweep_expired_watches_leaves_active_ones():
    conn = state.connect(":memory:")
    state.create_watch_request(
        conn, marketplace="ozon", cabinet_id=1, kind="ozon_draft_create",
        reference_json="{}", date_from="2026-09-20", date_to="2026-09-25",
        max_coefficient=0, requested_by_chat_id=555, now="2026-09-13T00:00:00",
    )

    expired = sweep_expired_watches(conn, now="2026-09-13T00:00:00")

    assert expired == []
    assert len(state.list_watch_requests(conn, status="watching")) == 1


class _RecordingTelegramClient:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text, buttons=None):
        self.sent.append((chat_id, text))


def test_build_scheduler_registers_both_jobs():
    conn = state.connect(":memory:")

    scheduler = build_scheduler(
        ozon_clients={},
        wb_clients={},
        conn=conn,
        telegram_client=_RecordingTelegramClient(),
        chat_id=555,
        watch_poll_seconds=90,
        fbs_poll_minutes=15,
        cooldown_minutes=60,
        now_fn=lambda: datetime.datetime(2026, 9, 13, 10, 0, 0),
        alert_hours_before_deadline=4.0,
        wb_assembly_hours=48.0,
    )

    assert {job.id for job in scheduler.get_jobs()} == {"poll_watches", "check_fbs_deadlines"}
