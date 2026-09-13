import json

from app.bot import state
from app.bot.booking_ozon import (
    poll_draft_watch,
    start_draft_booking,
    start_existing_draft_watch,
)


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


class _PendingThenResolvedOzonClient:
    """Simulates Ozon's async draft calculation: get_draft_id returns None on
    the first call (still CALCULATION_STATUS pending), then resolves to a real
    draft_id on subsequent calls."""

    def __init__(self, draft_id_responses, timeslots, resolved_draft_id="draft-1"):
        self._draft_id_responses = list(draft_id_responses)
        self._timeslots = timeslots
        self._resolved_draft_id = resolved_draft_id
        self.booked = []
        self.get_draft_id_calls = []

    def create_draft(self, items, warehouse_ids):
        return "op-1"

    def get_draft_id(self, operation_id):
        self.get_draft_id_calls.append(operation_id)
        return self._draft_id_responses.pop(0)

    def get_draft_timeslots(self, draft_id, date_from, date_to):
        assert draft_id == self._resolved_draft_id
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


def test_start_draft_booking_watches_when_draft_still_processing_then_poll_resolves_and_books():
    ozon = _PendingThenResolvedOzonClient(
        draft_id_responses=[None],
        timeslots=[],
    )
    conn = state.connect(":memory:")

    result = start_draft_booking(
        ozon, conn, cabinet_id=1, items=[{"sku": 1, "quantity": 10}], warehouse_ids=[507],
        date_from="2026-09-20", date_to="2026-09-25", chat_id=555, now="2026-09-13T10:00:00",
    )

    assert result["outcome"] == "watching"
    rows = state.list_watch_requests(conn, status="watching")
    assert len(rows) == 1
    reference = json.loads(rows[0]["reference_json"])
    assert reference["draft_id"] is None
    assert reference["operation_id"] == "op-1"

    # Ozon finishes calculating; a later poll resolves the draft_id and finds a free slot.
    ozon._draft_id_responses = ["draft-1"]
    ozon._timeslots = [
        {"warehouse_id": 507, "date": "2026-09-20", "coefficient": 0, "timeslot": {}}
    ]
    row = state.list_watch_requests(conn, status="watching")[0]

    message = poll_draft_watch(ozon, conn, row, now="2026-09-13T10:05:00")

    assert message is not None
    assert ozon.booked == [("draft-1", {})]
    assert state.list_watch_requests(conn, status="watching") == []
    assert state.list_watch_requests(conn, status="booked")[0]["id"] == rows[0]["id"]


def test_start_existing_draft_watch_books_free_slot_immediately():
    ozon = _FakeOzonClient(
        timeslots=[{"warehouse_id": 507, "date": "2026-09-20", "coefficient": 0, "timeslot": {}}]
    )
    conn = state.connect(":memory:")

    result = start_existing_draft_watch(
        ozon, conn, cabinet_id=1, draft_id="draft-existing", date_from="2026-09-20",
        date_to="2026-09-25", chat_id=555, now="2026-09-13T10:00:00",
    )

    assert result["outcome"] == "booked"
    assert ozon.booked == [("draft-existing", {})]


def test_start_existing_draft_watch_registers_watch_when_no_slots():
    ozon = _FakeOzonClient(timeslots=[])
    conn = state.connect(":memory:")

    result = start_existing_draft_watch(
        ozon, conn, cabinet_id=1, draft_id="draft-existing", date_from="2026-09-20",
        date_to="2026-09-25", chat_id=555, now="2026-09-13T10:00:00",
    )

    assert result["outcome"] == "watching"
    rows = state.list_watch_requests(conn, status="watching")
    assert json.loads(rows[0]["reference_json"])["draft_id"] == "draft-existing"
    assert rows[0]["kind"] == "ozon_draft_select"


def test_poll_draft_watch_returns_none_when_draft_still_processing():
    ozon = _PendingThenResolvedOzonClient(draft_id_responses=[None], timeslots=[])
    conn = state.connect(":memory:")
    state.create_watch_request(
        conn, marketplace="ozon", cabinet_id=1, kind="ozon_draft_create",
        reference_json=json.dumps({"draft_id": None, "operation_id": "op-1"}),
        date_from="2026-09-20", date_to="2026-09-25", max_coefficient=0,
        requested_by_chat_id=555, now="2026-09-13T10:00:00",
    )
    row = state.list_watch_requests(conn, status="watching")[0]

    message = poll_draft_watch(ozon, conn, row, now="2026-09-13T10:05:00")

    assert message is None
    assert ozon.booked == []
    assert ozon.get_draft_id_calls == ["op-1"]
    assert len(state.list_watch_requests(conn, status="watching")) == 1
