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


def _wb_client(handler):
    return WbClient(
        token="wb-tok",
        client=httpx.Client(
            base_url="https://supplies-api.wildberries.ru",
            transport=httpx.MockTransport(handler),
        ),
    )


def test_list_warehouses_returns_raw_list():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"ID": 507, "name": "Коледино"}])

    client = _wb_client(handler)

    assert client.list_warehouses() == [{"ID": 507, "name": "Коледино"}]


def test_get_acceptance_coefficients_passes_warehouse_ids():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["warehouseIDs"] = request.url.params.get("warehouseIDs")
        return httpx.Response(
            200, json=[{"warehouseID": 507, "date": "2026-09-20T00:00:00Z", "coefficient": 0}]
        )

    client = _wb_client(handler)

    coefficients = client.get_acceptance_coefficients([507, 508])

    assert seen["warehouseIDs"] == "507,508"
    assert coefficients[0]["coefficient"] == 0


def test_list_supplies_filters_by_status():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        return httpx.Response(200, json=[{"supplyID": 1, "statusID": 2}])

    client = _wb_client(handler)

    supplies = client.list_supplies(status_ids=[1, 2])

    assert supplies == [{"supplyID": 1, "statusID": 2}]
    assert b'"statusIDs":[1,2]' in seen["body"]
