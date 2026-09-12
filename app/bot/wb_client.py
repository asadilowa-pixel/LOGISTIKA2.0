import httpx

BASE_URL = "https://marketplace-api.wildberries.ru"


class WbClient:
    def __init__(self, token: str, client: httpx.Client | None = None):
        self._client = client or httpx.Client(
            base_url=BASE_URL, headers={"Authorization": token}
        )
        # Ensure Authorization header is set
        self._client.headers["Authorization"] = token

    def list_new_orders(self) -> list[dict]:
        resp = self._client.get("/api/v3/orders/new")
        resp.raise_for_status()
        return resp.json()["orders"]
