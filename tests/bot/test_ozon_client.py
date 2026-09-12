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
