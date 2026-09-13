import json

from app.bot import state
from app.bot.booking_ozon import poll_draft_watch, start_draft_booking


class _FakeOzonClient:
    def __init__(self, timeslots, draft_id="draft-1"):
        self._timeslots = timeslots
        self._draft_id = draft_id
        self.booked = []

    def create_draft(self, items, warehouse_ids):
        return "op-1"

    def get_draft_id(self, operation_id):
        return self._draft_id

    def get_draft_timeslots(self, draft_id, date_from, date_to):
        return self._timeslots

    def book_draft_timeslot(self, draft_id, timeslot):
        self.booked.append((draft_id, timeslot))
        return {"operation_id": "book-op-1"}


def test_start_draft_booking_books_free_slot_immediately():
    ozon = _FakeOzonClient(
        timeslots=[{"warehouse_id": 507, "date": "2026-09-20", "coefficient": 0, "timeslot": {}}]
    )
    conn = state.connect(":memory:")

    result = start_draft_booking(
        ozon, conn, cabinet_id=1, items=[{"sku": 1, "quantity": 10}], warehouse_ids=[507],
        date_from="2026-09-20", date_to="2026-09-25", chat_id=555, now="2026-09-13T10:00:00",
    )

    assert result["outcome"] == "booked"
    assert ozon.booked == [("draft-1", {})]
    assert state.list_watch_requests(conn, status="watching") == []


def test_start_draft_booking_requires_confirmation_for_paid_slot():
    ozon = _FakeOzonClient(
        timeslots=[{"warehouse_id": 507, "date": "2026-09-20", "coefficient": 3, "timeslot": {"cost": 500}}]
    )
    conn = state.connect(":memory:")

    result = start_draft_booking(
        ozon, conn, cabinet_id=1, items=[{"sku": 1, "quantity": 10}], warehouse_ids=[507],
        date_from="2026-09-20", date_to="2026-09-25", chat_id=555, now="2026-09-13T10:00:00",
    )

    assert result["outcome"] == "awaiting_confirmation"
    assert ozon.booked == []


def test_start_draft_booking_registers_watch_when_no_slots():
    ozon = _FakeOzonClient(timeslots=[])
    conn = state.connect(":memory:")

    result = start_draft_booking(
        ozon, conn, cabinet_id=1, items=[{"sku": 1, "quantity": 10}], warehouse_ids=[507],
        date_from="2026-09-20", date_to="2026-09-25", chat_id=555, now="2026-09-13T10:00:00",
    )

    assert result["outcome"] == "watching"
    rows = state.list_watch_requests(conn, status="watching")
    assert len(rows) == 1
    assert json.loads(rows[0]["reference_json"])["draft_id"] == "draft-1"


def test_poll_draft_watch_books_when_free_slot_appears():
    ozon = _FakeOzonClient(
        timeslots=[{"warehouse_id": 507, "date": "2026-09-20", "coefficient": 0, "timeslot": {}}]
    )
    conn = state.connect(":memory:")
    watch_id = state.create_watch_request(
        conn, marketplace="ozon", cabinet_id=1, kind="ozon_draft_create",
        reference_json=json.dumps({"draft_id": "draft-1"}), date_from="2026-09-20",
        date_to="2026-09-25", max_coefficient=0, requested_by_chat_id=555,
        now="2026-09-13T10:00:00",
    )
    row = state.list_watch_requests(conn, status="watching")[0]

    message = poll_draft_watch(ozon, conn, row, now="2026-09-13T10:05:00")

    assert message is not None
    assert ozon.booked == [("draft-1", {})]
    assert state.list_watch_requests(conn, status="booked")[0]["id"] == watch_id


def test_poll_draft_watch_returns_none_when_still_no_slot():
    ozon = _FakeOzonClient(timeslots=[])
    conn = state.connect(":memory:")
    state.create_watch_request(
        conn, marketplace="ozon", cabinet_id=1, kind="ozon_draft_create",
        reference_json=json.dumps({"draft_id": "draft-1"}), date_from="2026-09-20",
        date_to="2026-09-25", max_coefficient=0, requested_by_chat_id=555,
        now="2026-09-13T10:00:00",
    )
    row = state.list_watch_requests(conn, status="watching")[0]

    message = poll_draft_watch(ozon, conn, row, now="2026-09-13T10:05:00")

    assert message is None
    assert len(state.list_watch_requests(conn, status="watching")) == 1
