import datetime

from app.bot.handlers import handle_status_command, parse_update


def test_parse_update_extracts_command_from_message_created():
    update = {
        "update_type": "message_created",
        "message": {
            "recipient": {"chat_id": 555},
            "body": {"text": "/status"},
        },
    }

    parsed = parse_update(update)

    assert parsed == {"kind": "command", "chat_id": 555, "text": "/status"}


def test_parse_update_extracts_callback():
    update = {
        "update_type": "message_callback",
        "callback": {"callback_id": "cb-1", "payload": "wh-507"},
        "message": {"recipient": {"chat_id": 555}},
    }

    parsed = parse_update(update)

    assert parsed == {"kind": "callback", "chat_id": 555, "callback_id": "cb-1", "payload": "wh-507"}


def test_parse_update_ignores_unknown_types():
    assert parse_update({"update_type": "bot_added"}) is None


class _RecordingMaxClient:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text, buttons=None):
        self.sent.append((chat_id, text))


def test_handle_status_command_sends_summary_for_each_cabinet():
    max_client = _RecordingMaxClient()
    now = datetime.datetime.fromisoformat("2026-09-13T06:00:00+00:00")
    cabinets_data = [
        ("ozon", 1, [{"posting_number": "P-1", "shipment_date": "2026-09-13T10:00:00+00:00"}]),
        ("wb", 2, []),
    ]

    handle_status_command(max_client, chat_id=555, cabinets_data=cabinets_data, now=now)

    assert len(max_client.sent) == 1
    chat_id, text = max_client.sent[0]
    assert chat_id == 555
    assert "ozon (кабинет 1)" in text
    assert "wb (кабинет 2): нет заказов к отгрузке" in text
