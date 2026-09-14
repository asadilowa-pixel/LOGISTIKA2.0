import datetime

from app.bot import state
from app.bot.handlers import handle_cancel_command, handle_status_command, parse_update


def test_parse_update_extracts_command_from_message():
    update = {
        "update_id": 1,
        "message": {"chat": {"id": 555}, "text": "/status"},
    }

    parsed = parse_update(update)

    assert parsed == {"kind": "command", "chat_id": 555, "text": "/status"}


def test_parse_update_extracts_callback():
    update = {
        "update_id": 2,
        "callback_query": {"id": "cb-1", "data": "wh-507", "message": {"chat": {"id": 555}}},
    }

    parsed = parse_update(update)

    assert parsed == {"kind": "callback", "chat_id": 555, "callback_id": "cb-1", "payload": "wh-507"}


def test_parse_update_ignores_unknown_types():
    assert parse_update({"update_id": 3, "my_chat_member": {}}) is None


class _RecordingTelegramClient:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text, buttons=None):
        self.sent.append((chat_id, text))


def test_handle_status_command_sends_summary_for_each_cabinet():
    telegram_client = _RecordingTelegramClient()
    now = datetime.datetime.fromisoformat("2026-09-13T06:00:00+00:00")
    cabinets_data = [
        ("ozon", 1, [{"posting_number": "P-1", "shipment_date": "2026-09-13T10:00:00+00:00"}]),
        ("wb", 2, []),
    ]

    handle_status_command(telegram_client, chat_id=555, cabinets_data=cabinets_data, now=now)

    assert len(telegram_client.sent) == 1
    chat_id, text = telegram_client.sent[0]
    assert chat_id == 555
    assert "ozon (кабинет 1)" in text
    assert "wb (кабинет 2): нет заказов к отгрузке" in text


def test_handle_cancel_command_marks_watch_cancelled():
    conn = state.connect(":memory:")
    watch_id = state.create_watch_request(
        conn, marketplace="ozon", cabinet_id=1, kind="ozon_draft_create",
        reference_json="{}", date_from="2026-09-20", date_to="2026-09-25",
        max_coefficient=0, requested_by_chat_id=555, now="2026-09-13T10:00:00",
    )

    reply = handle_cancel_command(conn, chat_id=555, args=[str(watch_id)], now="2026-09-13T10:10:00")

    assert str(watch_id) in reply
    assert state.list_watch_requests(conn, status="watching") == []


def test_handle_cancel_command_reports_unknown_watch():
    conn = state.connect(":memory:")

    reply = handle_cancel_command(conn, chat_id=555, args=["999"], now="2026-09-13T10:10:00")

    assert "не найдено" in reply
