import datetime

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
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff_from = (now - datetime.timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        cutoff_to = (now + datetime.timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")

        postings: list[dict] = []
        offset = 0
        while True:
            resp = self._client.post(
                "/v3/posting/fbs/unfulfilled/list",
                json={
                    "dir": "asc",
                    "filter": {"cutoff_from": cutoff_from, "cutoff_to": cutoff_to},
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

    def create_draft(self, items: list[dict], warehouse_ids: list[int]) -> str:
        resp = self._client.post(
            "/v1/draft/create",
            json={"items": items, "drop_off_point_warehouse_id": warehouse_ids[0]},
        )
        resp.raise_for_status()
        return resp.json()["operation_id"]

    def get_draft_id(self, operation_id: str) -> str | None:
        resp = self._client.post("/v1/draft/create/info", json={"operation_id": operation_id})
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") != "CALCULATION_STATUS_SUCCESS":
            return None
        return body["draft_id"]

    def get_draft_timeslots(self, draft_id: str, date_from: str, date_to: str) -> list[dict]:
        resp = self._client.post(
            "/v2/draft/timeslot/info",
            json={"draft_id": draft_id, "date_from": date_from, "date_to": date_to},
        )
        resp.raise_for_status()
        body = resp.json()
        slots = []
        for warehouse in body.get("drop_off_warehouse_timeslots", []):
            for day in warehouse.get("days", []):
                for timeslot in day.get("timeslots", []):
                    slots.append(
                        {
                            "warehouse_id": warehouse["warehouse_id"],
                            "date": day["date"],
                            "coefficient": timeslot["coefficient"],
                            "timeslot": timeslot,
                        }
                    )
        return slots

    def book_draft_timeslot(self, draft_id: str, timeslot: dict) -> dict:
        resp = self._client.post(
            "/v1/draft/supply/create", json={"draft_id": draft_id, "timeslot": timeslot}
        )
        resp.raise_for_status()
        return resp.json()
