import httpx

from app.bot.telegram_client import TelegramClient


def _client_with(handler):
    return httpx.Client(
        base_url="https://api.telegram.org/bottok-123", transport=httpx.MockTransport(handler)
    )


def test_get_updates_sends_offset_and_timeout():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["offset"] = request.url.params.get("offset")
        seen["timeout"] = request.url.params.get("timeout")
        return httpx.Response(200, json={"ok": True, "result": []})

    client = TelegramClient(token="tok-123", client=_client_with(handler))
    result = client.get_updates(offset=7)

    assert seen["path"] == "/bottok-123/getUpdates"
    assert seen["offset"] == "7"
    assert seen["timeout"] == "30"
    assert result == {"ok": True, "result": []}


def test_send_message_posts_chat_id_and_text_in_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.read()
        return httpx.Response(200, json={"ok": True})

    client = TelegramClient(token="tok-123", client=_client_with(handler))
    client.send_message(chat_id=555, text="hi")

    assert seen["path"] == "/bottok-123/sendMessage"
    assert b'"chat_id":555' in seen["body"]
    assert b'"text":"hi"' in seen["body"]


def test_send_message_with_buttons_includes_inline_keyboard():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        return httpx.Response(200, json={"ok": True})

    client = TelegramClient(token="tok-123", client=_client_with(handler))
    client.send_message(
        chat_id=555, text="Выберите склад",
        buttons=[[{"text": "Коледино", "callback_data": "wh-507"}]],
    )

    assert b"inline_keyboard" in seen["body"]
    assert b"wh-507" in seen["body"]


def test_answer_callback_posts_callback_query_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.read()
        return httpx.Response(200, json={"ok": True})

    client = TelegramClient(token="tok-123", client=_client_with(handler))
    client.answer_callback(callback_id="cb-1", text="Забронировано")

    assert seen["path"] == "/bottok-123/answerCallbackQuery"
    assert b'"callback_query_id":"cb-1"' in seen["body"]
