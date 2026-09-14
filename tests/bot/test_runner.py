import asyncio
import time

from app.bot import state
from app.bot.runner import BotContext, dispatch_callback, dispatch_command, poll_once, run_forever


class _FakeTelegramClient:
    def __init__(self, batches):
        self._batches = batches
        self.calls = 0

    def get_updates(self, offset=None, timeout=30, limit=100):
        batch = self._batches[self.calls]
        self.calls += 1
        return batch


def test_poll_once_dispatches_command_and_returns_next_offset():
    telegram_client = _FakeTelegramClient(
        [
            {
                "result": [
                    {"update_id": 41, "message": {"chat": {"id": 555}, "text": "/status"}}
                ],
            }
        ]
    )
    seen_commands = []

    new_offset = poll_once(
        telegram_client,
        offset=None,
        on_command=lambda chat_id, text: seen_commands.append((chat_id, text)),
        on_callback=lambda chat_id, callback_id, payload: None,
    )

    assert new_offset == 42
    assert seen_commands == [(555, "/status")]


def test_poll_once_dispatches_callback():
    telegram_client = _FakeTelegramClient(
        [
            {
                "result": [
                    {
                        "update_id": 42,
                        "callback_query": {
                            "id": "cb-1", "data": "wh-507", "message": {"chat": {"id": 555}}
                        },
                    }
                ],
            }
        ]
    )
    seen_callbacks = []

    poll_once(
        telegram_client,
        offset=None,
        on_command=lambda chat_id, text: None,
        on_callback=lambda chat_id, callback_id, payload: seen_callbacks.append(
            (chat_id, callback_id, payload)
        ),
    )

    assert seen_callbacks == [(555, "cb-1", "wh-507")]


def test_poll_once_ignores_unknown_update_types():
    telegram_client = _FakeTelegramClient([{"result": [{"update_id": 1, "my_chat_member": {}}]}])

    new_offset = poll_once(
        telegram_client, offset=None, on_command=lambda *a: None, on_callback=lambda *a: None
    )

    assert new_offset == 2


def test_poll_once_keeps_offset_when_no_updates():
    telegram_client = _FakeTelegramClient([{"result": []}])

    new_offset = poll_once(
        telegram_client, offset=7, on_command=lambda *a: None, on_callback=lambda *a: None
    )

    assert new_offset == 7


class _SlowTelegramClient:
    def get_updates(self, offset=None, timeout=30, limit=100):
        time.sleep(0.05)
        return {"result": []}


class _FakeScheduler:
    def __init__(self):
        self.shutdown_called = False

    def start(self):
        pass

    def shutdown(self, wait=False):
        self.shutdown_called = True


def test_run_forever_does_not_block_the_event_loop():
    context = BotContext(
        telegram_client=_SlowTelegramClient(), conn=None, ozon_clients={}, wb_clients={},
        allowed_chat_ids={555}, scheduler=_FakeScheduler(),
    )

    async def scenario():
        task = asyncio.create_task(run_forever(context))
        ticks = 0
        for _ in range(5):
            await asyncio.sleep(0.01)
            ticks += 1
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return ticks

    ticks = asyncio.run(asyncio.wait_for(scenario(), timeout=2.0))

    assert ticks == 5
    assert context.scheduler.shutdown_called


class _FlakyTelegramClient:
    def __init__(self):
        self.calls = 0

    def get_updates(self, offset=None, timeout=30, limit=100):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("boom")
        return {"result": []}


def test_run_forever_survives_a_poll_failure():
    client = _FlakyTelegramClient()
    context = BotContext(
        telegram_client=client, conn=None, ozon_clients={}, wb_clients={},
        allowed_chat_ids={555}, scheduler=_FakeScheduler(),
    )

    async def scenario():
        task = asyncio.create_task(run_forever(context))
        for _ in range(5):
            await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return client.calls

    calls = asyncio.run(asyncio.wait_for(scenario(), timeout=2.0))

    assert calls >= 2


class _RecordingTelegramClient:
    def __init__(self):
        self.sent = []
        self.answered = []

    def send_message(self, chat_id, text, buttons=None):
        self.sent.append((chat_id, text, buttons))

    def answer_callback(self, callback_id, text=None):
        self.answered.append((callback_id, text))


class _FakeOzonClient:
    def __init__(self, postings):
        self._postings = postings

    def list_unfulfilled_postings(self):
        return self._postings


class _FakeWbClient:
    def __init__(self, orders):
        self._orders = orders

    def list_new_orders(self):
        return self._orders


def _context(**overrides):
    defaults = dict(
        telegram_client=_RecordingTelegramClient(),
        conn=state.connect(":memory:"),
        ozon_clients={1: _FakeOzonClient([])},
        wb_clients={2: _FakeWbClient([])},
        allowed_chat_ids={555},
        scheduler=_FakeScheduler(),
    )
    defaults.update(overrides)
    return BotContext(**defaults)


def test_dispatch_command_ignores_chat_outside_allowlist():
    context = _context()

    dispatch_command(context, 999, "/status")

    assert context.telegram_client.sent == []


def test_dispatch_command_status_sends_summary():
    context = _context()

    dispatch_command(context, 555, "/status")

    assert len(context.telegram_client.sent) == 1
    assert context.telegram_client.sent[0][0] == 555


def test_dispatch_command_start_sends_menu():
    context = _context()

    dispatch_command(context, 555, "/start")

    assert len(context.telegram_client.sent) == 1
    _chat_id, _text, buttons = context.telegram_client.sent[0]
    assert buttons is not None


def test_dispatch_command_cancel_sends_reply():
    context = _context()
    watch_id = state.create_watch_request(
        context.conn, marketplace="ozon", cabinet_id=1, kind="ozon_draft_create",
        reference_json="{}", date_from="2026-09-20", date_to="2026-09-25",
        max_coefficient=0, requested_by_chat_id=555, now="2026-09-13T10:00:00",
    )

    dispatch_command(context, 555, f"/cancel {watch_id}")

    assert len(context.telegram_client.sent) == 1
    chat_id, text, _buttons = context.telegram_client.sent[0]
    assert chat_id == 555
    assert "отменено" in text


def test_dispatch_callback_ignores_chat_outside_allowlist():
    context = _context()

    dispatch_callback(context, 999, "cb-1", "menu:status")

    assert context.telegram_client.sent == []
    assert context.telegram_client.answered == []


def test_dispatch_callback_menu_status_sends_summary_and_answers():
    context = _context()

    dispatch_callback(context, 555, "cb-1", "menu:status")

    assert len(context.telegram_client.sent) == 1
    assert context.telegram_client.answered == [("cb-1", None)]


def test_dispatch_callback_menu_cancel_list_sends_list_and_answers():
    context = _context()

    dispatch_callback(context, 555, "cb-1", "menu:cancel_list")

    assert len(context.telegram_client.sent) == 1
    assert context.telegram_client.answered == [("cb-1", None)]


def test_dispatch_callback_cancel_watch_cancels_and_answers():
    context = _context()
    watch_id = state.create_watch_request(
        context.conn, marketplace="ozon", cabinet_id=1, kind="ozon_draft_create",
        reference_json="{}", date_from="2026-09-20", date_to="2026-09-25",
        max_coefficient=0, requested_by_chat_id=555, now="2026-09-13T10:00:00",
    )

    dispatch_callback(context, 555, "cb-1", f"cancel:{watch_id}")

    assert state.list_watch_requests(context.conn, status="watching") == []
    [(callback_id, text)] = context.telegram_client.answered
    assert callback_id == "cb-1"
    assert "отменено" in text
