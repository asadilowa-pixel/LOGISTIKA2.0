import httpx

BASE_URL = "https://api.telegram.org"


class TelegramClient:
    def __init__(self, token: str, client: httpx.Client | None = None):
        self._client = client or httpx.Client(base_url=f"{BASE_URL}/bot{token}")

    def get_updates(self, offset: int | None = None, timeout: int = 30, limit: int = 100) -> dict:
        params: dict = {"timeout": timeout, "limit": limit}
        if offset is not None:
            params["offset"] = offset
        resp = self._client.get("/getUpdates", params=params, timeout=timeout + 10)
        resp.raise_for_status()
        return resp.json()

    def send_message(
        self, chat_id: int, text: str, buttons: list[list[dict]] | None = None
    ) -> dict:
        payload: dict = {"chat_id": chat_id, "text": text}
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        resp = self._client.post("/sendMessage", json=payload)
        resp.raise_for_status()
        return resp.json()

    def answer_callback(self, callback_id: str, text: str | None = None) -> dict:
        payload: dict = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text
        resp = self._client.post("/answerCallbackQuery", json=payload)
        resp.raise_for_status()
        return resp.json()
