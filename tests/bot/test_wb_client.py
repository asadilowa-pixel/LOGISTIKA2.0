import httpx

from app.bot.wb_client import WbClient


def test_list_new_orders_sends_auth_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"orders": [{"orderUid": "O-1"}]})

    client = WbClient(
        token="wb-tok",
        client=httpx.Client(
            base_url="https://marketplace-api.wildberries.ru",
            transport=httpx.MockTransport(handler),
        ),
    )

    orders = client.list_new_orders()

    assert seen["auth"] == "wb-tok"
    assert orders == [{"orderUid": "O-1"}]
