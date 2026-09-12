import httpx

BASE_URL = "https://platform-api2.max.ru"


class MaxClient:
    def __init__(self, token: str, client: httpx.Client | None = None):
        self._client = client or httpx.Client(
            base_url=BASE_URL, headers={"Authorization": token}
        )
        # Ensure Authorization header is set
        self._client.headers["Authorization"] = token

    def get_updates(self, marker: int | None = None, timeout: int = 30, limit: int = 100) -> dict:
        params = {"timeout": timeout, "limit": limit}
        if marker is not None:
            params["marker"] = marker
        resp = self._client.get("/updates", params=params, timeout=timeout + 10)
        resp.raise_for_status()
        return resp.json()

    def send_message(
        self, chat_id: int, text: str, buttons: list[list[dict]] | None = None
    ) -> dict:
        payload: dict = {"text": text}
        if buttons:
            payload["attachments"] = [
                {"type": "inline_keyboard", "payload": {"buttons": buttons}}
            ]
        resp = self._client.post("/messages", params={"chat_id": chat_id}, json=payload)
        resp.raise_for_status()
        return resp.json()

    def answer_callback(self, callback_id: str, text: str | None = None) -> dict:
        payload: dict = {}
        if text:
            payload["message"] = {"text": text}
        resp = self._client.post("/answers", params={"callback_id": callback_id}, json=payload)
        resp.raise_for_status()
        return resp.json()
