import httpx

BASE_URL = "https://api-seller.ozon.ru"


class OzonClient:
    def __init__(self, client_id: str, api_key: str, client: httpx.Client | None = None):
        self._client = client or httpx.Client(
            base_url=BASE_URL,
            headers={"Client-Id": client_id, "Api-Key": api_key},
        )
        # Ensure headers are set
        self._client.headers["Client-Id"] = client_id
        self._client.headers["Api-Key"] = api_key

    def list_unfulfilled_postings(self, limit: int = 1000) -> list[dict]:
        postings: list[dict] = []
        offset = 0
        while True:
            resp = self._client.post(
                "/v3/posting/fbs/unfulfilled/list",
                json={
                    "dir": "asc",
                    "filter": {},
                    "limit": limit,
                    "offset": offset,
                    "with": {"analytics_data": False},
                },
            )
            resp.raise_for_status()
            result = resp.json()["result"]
            postings.extend(result["postings"])
            if not result.get("has_next"):
                break
            offset += limit
        return postings
