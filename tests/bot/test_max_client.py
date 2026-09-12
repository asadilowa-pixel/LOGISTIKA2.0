import httpx

from app.bot.max_client import MaxClient


def _client_with(handler):
    return httpx.Client(base_url="https://platform-api2.max.ru", transport=httpx.MockTransport(handler))


def test_get_updates_sends_marker_and_auth_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["marker"] = request.url.params.get("marker")
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"updates": [], "marker": 42})

    client = MaxClient(token="tok-123", client=_client_with(handler))
    result = client.get_updates(marker=7)

    assert seen["path"] == "/updates"
    assert seen["marker"] == "7"
    assert seen["auth"] == "tok-123"
    assert result == {"updates": [], "marker": 42}


def test_send_message_posts_text_and_chat_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["chat_id"] = request.url.params.get("chat_id")
        seen["body"] = request.read()
        return httpx.Response(200, json={"message": {"body": {"text": "hi"}}})

    client = MaxClient(token="tok-123", client=_client_with(handler))
    client.send_message(chat_id=555, text="hi")

    assert seen["chat_id"] == "555"
    assert b'"text":"hi"' in seen["body"]


def test_send_message_with_buttons_includes_inline_keyboard():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        return httpx.Response(200, json={})

    client = MaxClient(token="tok-123", client=_client_with(handler))
    client.send_message(
        chat_id=555, text="Выберите склад",
        buttons=[[{"type": "callback", "text": "Коледино", "payload": "wh-507"}]],
    )

    assert b"inline_keyboard" in seen["body"]
    assert b"wh-507" in seen["body"]


def test_answer_callback_posts_callback_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["callback_id"] = request.url.params.get("callback_id")
        return httpx.Response(200, json={})

    client = MaxClient(token="tok-123", client=_client_with(handler))
    client.answer_callback(callback_id="cb-1", text="Забронировано")

    assert seen["callback_id"] == "cb-1"
