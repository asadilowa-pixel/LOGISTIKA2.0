import asyncio
import time

from app.bot.runner import BotContext, poll_once, run_forever


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
        chat_id=555, scheduler=_FakeScheduler(),
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
