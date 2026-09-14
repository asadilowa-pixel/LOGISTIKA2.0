import json

import httpx

from app.bot.ozon_client import OzonClient


def _client_with(handler):
    return httpx.Client(base_url="https://api-seller.ozon.ru", transport=httpx.MockTransport(handler))


def test_list_unfulfilled_postings_single_page():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Client-Id"] == "111"
        assert request.headers["Api-Key"] == "key-1"
        return httpx.Response(
            200,
            json={"result": {"postings": [{"posting_number": "P-1"}], "has_next": False}},
        )

    client = OzonClient(client_id="111", api_key="key-1", client=_client_with(handler))

    postings = client.list_unfulfilled_postings()

    assert postings == [{"posting_number": "P-1"}]


def test_list_unfulfilled_postings_sends_cutoff_date_range():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json={"result": {"postings": [], "has_next": False}})

    client = OzonClient(client_id="111", api_key="key-1", client=_client_with(handler))

    client.list_unfulfilled_postings()

    filter_ = seen["body"]["filter"]
    assert filter_["cutoff_from"]
    assert filter_["cutoff_to"]
    assert filter_["cutoff_from"] < filter_["cutoff_to"]


def test_list_unfulfilled_postings_paginates():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.read())
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={"result": {"postings": [{"posting_number": "P-1"}], "has_next": True}},
            )
        return httpx.Response(
            200,
            json={"result": {"postings": [{"posting_number": "P-2"}], "has_next": False}},
        )

    client = OzonClient(client_id="111", api_key="key-1", client=_client_with(handler))

    postings = client.list_unfulfilled_postings(limit=1)

    assert [p["posting_number"] for p in postings] == ["P-1", "P-2"]
    assert len(calls) == 2


def test_create_draft_returns_operation_id():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"operation_id": "op-1"})

    client = OzonClient(client_id="111", api_key="key-1", client=_client_with(handler))

    operation_id = client.create_draft(
        items=[{"sku": 1, "quantity": 10}], warehouse_ids=[507]
    )

    assert operation_id == "op-1"


def test_get_draft_id_returns_none_while_processing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "CALCULATION_STATUS_IN_PROGRESS"})

    client = OzonClient(client_id="111", api_key="key-1", client=_client_with(handler))

    assert client.get_draft_id("op-1") is None


def test_get_draft_id_returns_id_when_ready():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"status": "CALCULATION_STATUS_SUCCESS", "draft_id": "draft-1"}
        )

    client = OzonClient(client_id="111", api_key="key-1", client=_client_with(handler))

    assert client.get_draft_id("op-1") == "draft-1"


def test_get_draft_timeslots_returns_list():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "drop_off_warehouse_timeslots": [
                    {
                        "warehouse_id": 507,
                        "days": [
                            {
                                "date": "2026-09-20",
                                "timeslots": [{"from_in_timezone": "10:00", "coefficient": 0}],
                            }
                        ],
                    }
                ]
            },
        )

    client = OzonClient(client_id="111", api_key="key-1", client=_client_with(handler))

    timeslots = client.get_draft_timeslots("draft-1", date_from="2026-09-20", date_to="2026-09-25")

    assert timeslots == [
        {"warehouse_id": 507, "date": "2026-09-20", "coefficient": 0,
         "timeslot": {"from_in_timezone": "10:00", "coefficient": 0}}
    ]


def test_book_draft_timeslot_posts_choice():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        return httpx.Response(200, json={"operation_id": "book-op-1"})

    client = OzonClient(client_id="111", api_key="key-1", client=_client_with(handler))

    result = client.book_draft_timeslot(
        "draft-1", timeslot={"warehouse_id": 507, "date": "2026-09-20", "from_in_timezone": "10:00"}
    )

    assert result == {"operation_id": "book-op-1"}
    assert b"draft-1" in seen["body"]
