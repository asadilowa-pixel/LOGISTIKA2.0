"""Выгрузка FBO-поставок Ozon (в пути и принятые) за период в CSV.

Строка отчёта = товар в поставке: дата, номер заявки, статус, склад, артикул, SKU,
название, количество отгружено (из состава поставки) и количество принято.

Принятое количество: Seller API отдаёт в составе поставки (/v1/supply-order/bundle)
только заявленное количество `quantity`. Если в ответе встретится поле приёмки
(ключ с "accept"/"received" в названии), скрипт подставит его; иначе колонка
«Принято» останется пустой, а сырые ответы API сохранятся в *_raw.json для проверки.

Usage:
    OZON_CLIENT_ID=... OZON_API_KEY=... \\
        python scripts/ozon_supplies_report.py --date-from 2026-08-01 --date-to 2026-09-30

Не требует зависимостей кроме стандартной библиотеки Python 3.10+.
"""

import argparse
import csv
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = "https://api-seller.ozon.ru"

# «В пути» и «принятые» статусы заявки на поставку.
IN_TRANSIT_STATES = ["ACCEPTED_AT_SUPPLY_WAREHOUSE", "IN_TRANSIT"]
ACCEPTED_STATES = [
    "ACCEPTANCE_AT_STORAGE_WAREHOUSE",
    "REPORTS_CONFIRMATION_AWAITING",
    "REPORT_REJECTED",
    "COMPLETED",
]

STATE_NAMES = {
    "ACCEPTED_AT_SUPPLY_WAREHOUSE": "Принята на точке отгрузки",
    "IN_TRANSIT": "В пути",
    "ACCEPTANCE_AT_STORAGE_WAREHOUSE": "Приёмка на складе",
    "REPORTS_CONFIRMATION_AWAITING": "Согласование актов",
    "REPORT_REJECTED": "Спор по актам",
    "COMPLETED": "Завершена",
}

ACCEPTED_KEY_HINTS = ("accept", "received")

CSV_COLUMNS = [
    "Дата поставки",
    "Дата создания заявки",
    "Номер заявки",
    "ID заявки",
    "ID поставки",
    "Статус",
    "Склад",
    "Артикул",
    "SKU",
    "Название",
    "Отгружено, шт",
    "Принято, шт",
]


class OzonApi:
    def __init__(self, client_id: str, api_key: str, base_url: str = BASE_URL):
        self._base_url = base_url
        self._headers = {
            "Client-Id": client_id,
            "Api-Key": api_key,
            "Content-Type": "application/json",
        }
        self.raw: list[dict] = []

    def post(self, path: str, body: dict, retries: int = 5) -> dict:
        data = json.dumps(body).encode()
        for attempt in range(retries):
            req = urllib.request.Request(
                self._base_url + path, data=data, headers=self._headers, method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read())
                    self.raw.append({"path": path, "request": body, "response": result})
                    return result
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(f"{path}: HTTP {e.code}: {e.read().decode(errors='replace')}")
        raise RuntimeError(f"{path}: rate limit, попытки исчерпаны")

    def list_order_ids(self, states: list[str]) -> list[int]:
        order_ids: list[int] = []
        last_id = ""
        while True:
            body = {
                "filter": {"states": states},
                "limit": 100,
                "sort_by": "ORDER_CREATION",
                "sort_dir": "DESC",
            }
            if last_id:
                body["last_id"] = last_id
            result = self.post("/v3/supply-order/list", body)
            page = result.get("order_ids") or []
            order_ids.extend(page)
            last_id = result.get("last_id") or ""
            if not page or not last_id:
                return order_ids

    def get_orders(self, order_ids: list[int]) -> list[dict]:
        orders: list[dict] = []
        for i in range(0, len(order_ids), 50):
            result = self.post("/v3/supply-order/get", {"order_ids": order_ids[i : i + 50]})
            orders.extend(result.get("orders") or [])
        return orders

    def get_bundle_items(self, bundle_id: str) -> list[dict]:
        items: list[dict] = []
        last_id = ""
        while True:
            body = {"bundle_ids": [bundle_id], "limit": 100, "is_asc": True}
            if last_id:
                body["last_id"] = last_id
            result = self.post("/v1/supply-order/bundle", body)
            items.extend(result.get("items") or [])
            last_id = result.get("last_id") or ""
            if not result.get("has_next") or not last_id:
                return items


def parse_dt(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def supply_date(order: dict) -> datetime.datetime | None:
    """Дата поставки: начало таймслота, иначе дата прибытия на склад, иначе создание заявки."""
    timeslot = ((order.get("timeslot") or {}).get("timeslot") or {}).get("from")
    if timeslot:
        return parse_dt(timeslot)
    for supply in order.get("supplies") or []:
        arrival = (supply.get("storage_warehouse") or {}).get("arrival_date")
        if arrival:
            return parse_dt(arrival)
    return parse_dt(order.get("created_date"))


def accepted_quantity(item: dict) -> int | None:
    for key, value in item.items():
        if any(hint in key.lower() for hint in ACCEPTED_KEY_HINTS) and isinstance(value, int):
            return value
    return None


def build_rows(
    api: OzonApi, orders: list[dict], date_from: datetime.date, date_to: datetime.date
) -> list[dict]:
    rows = []
    for order in orders:
        when = supply_date(order)
        if when is None or not (date_from <= when.date() <= date_to):
            continue
        created = parse_dt(order.get("created_date"))
        for supply in order.get("supplies") or []:
            bundle_id = supply.get("bundle_id")
            if not bundle_id:
                continue
            warehouse = (supply.get("storage_warehouse") or {}).get("name", "")
            state = order.get("state", "")
            for item in api.get_bundle_items(bundle_id):
                accepted = accepted_quantity(item)
                rows.append(
                    {
                        "Дата поставки": when.date().isoformat(),
                        "Дата создания заявки": created.date().isoformat() if created else "",
                        "Номер заявки": order.get("order_number", ""),
                        "ID заявки": order.get("order_id", ""),
                        "ID поставки": supply.get("supply_id", ""),
                        "Статус": STATE_NAMES.get(state, state),
                        "Склад": warehouse,
                        "Артикул": item.get("offer_id", ""),
                        "SKU": item.get("sku", ""),
                        "Название": item.get("name", ""),
                        "Отгружено, шт": item.get("quantity", ""),
                        "Принято, шт": "" if accepted is None else accepted,
                    }
                )
    rows.sort(key=lambda r: (r["Дата поставки"], str(r["Номер заявки"]), r["Артикул"]))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date-from", default="2026-08-01")
    parser.add_argument("--date-to", default="2026-09-30")
    parser.add_argument("--out", default="ozon_supplies.csv")
    args = parser.parse_args()

    client_id = os.environ.get("OZON_CLIENT_ID")
    api_key = os.environ.get("OZON_API_KEY")
    if not client_id or not api_key:
        print("Задайте переменные окружения OZON_CLIENT_ID и OZON_API_KEY", file=sys.stderr)
        return 2

    date_from = datetime.date.fromisoformat(args.date_from)
    date_to = datetime.date.fromisoformat(args.date_to)

    api = OzonApi(client_id, api_key)
    order_ids = api.list_order_ids(IN_TRANSIT_STATES + ACCEPTED_STATES)
    orders = api.get_orders(order_ids)
    rows = build_rows(api, orders, date_from, date_to)

    # utf-8-sig и ";" — чтобы Excel сразу открыл файл с кириллицей по колонкам.
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    raw_path = os.path.splitext(args.out)[0] + "_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(api.raw, f, ensure_ascii=False, indent=1)

    shipped = sum(r["Отгружено, шт"] or 0 for r in rows)
    accepted = [r["Принято, шт"] for r in rows if r["Принято, шт"] != ""]
    print(f"Заявок всего: {len(orders)}, строк за период: {len(rows)}, отгружено: {shipped} шт")
    if accepted:
        print(f"Принято: {sum(accepted)} шт")
    else:
        print(f"Поле приёмки в ответе API не найдено — проверьте {raw_path}")
    print(f"Сохранено: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
