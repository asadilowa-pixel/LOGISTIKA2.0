from app.bot import state
from app.bot.runner import poll_once


class _FakeMaxClient:
    def __init__(self, batches):
        self._batches = batches
        self.calls = 0

    def get_updates(self, marker=None, timeout=30, limit=100):
        batch = self._batches[self.calls]
        self.calls += 1
        return batch


def test_poll_once_dispatches_command_and_returns_new_marker():
    max_client = _FakeMaxClient(
        [
            {
                "updates": [
                    {
                        "update_type": "message_created",
                        "message": {"recipient": {"chat_id": 555}, "body": {"text": "/status"}},
                    }
                ],
                "marker": 42,
            }
        ]
    )
    seen_commands = []

    new_marker = poll_once(
        max_client,
        marker=None,
        on_command=lambda chat_id, text: seen_commands.append((chat_id, text)),
        on_callback=lambda chat_id, callback_id, payload: None,
    )

    assert new_marker == 42
    assert seen_commands == [(555, "/status")]


def test_poll_once_dispatches_callback():
    max_client = _FakeMaxClient(
        [
            {
                "updates": [
                    {
                        "update_type": "message_callback",
                        "callback": {"callback_id": "cb-1", "payload": "wh-507"},
                        "message": {"recipient": {"chat_id": 555}},
                    }
                ],
                "marker": 43,
            }
        ]
    )
    seen_callbacks = []

    poll_once(
        max_client,
        marker=None,
        on_command=lambda chat_id, text: None,
        on_callback=lambda chat_id, callback_id, payload: seen_callbacks.append(
            (chat_id, callback_id, payload)
        ),
    )

    assert seen_callbacks == [(555, "cb-1", "wh-507")]


def test_poll_once_ignores_unknown_update_types():
    max_client = _FakeMaxClient([{"updates": [{"update_type": "bot_added"}], "marker": 1}])

    poll_once(
        max_client, marker=None, on_command=lambda *a: None, on_callback=lambda *a: None
    )
