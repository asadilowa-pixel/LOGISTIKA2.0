"""Выгрузка FBO-поставок Ozon (в пути и принятые) за период в CSV.

Строка отчёта = товар в поставке: дата, номер заявки, статус, склад, артикул, SKU,
название, количество отгружено (из состава поставки) и количество принято.

Принятое количество: Seller API не отдаёт факт приёмки по товарам, но отдаёт статус
каждого грузоместа (/v1/cargoes/get) и его состав (/v1/supply-order/bundle). «Принято» —
товары в грузоместах со статусом PROCESSED, «Утеряно» — в грузоместах LOST, остальное —
«На приёмке / в пути». Расхождения внутри принятой коробки (недовложение, брак) API
не показывает — их видно только в актах приёмки в личном кабинете.

Usage:
    OZON_CLIENT_ID=... OZON_API_KEY=... \\
        python scripts/ozon_supplies_report.py --date-from 2026-08-01 --date-to 2026-09-30

Не требует зависимостей кроме стандартной библиотеки Python 3.10+.
"""

import argparse
import concurrent.futures
import csv
import datetime
import json
import os
import random
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

CARGO_ACCEPTED = "PROCESSED"
CARGO_LOST = "LOST"

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
    "Утеряно, шт",
    "На приёмке / в пути, шт",
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
        self._bundle_cache: dict[str, list[dict]] = {}

    def post(self, path: str, body: dict, retries: int = 12) -> dict:
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
                    time.sleep(min(2**attempt, 10) * (0.5 + random.random()))
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

    def get_cargoes(self, supply_ids: list[int]) -> dict[int, list[dict]]:
        cargoes: dict[int, list[dict]] = {}
        for i in range(0, len(supply_ids), 100):
            result = self.post("/v1/cargoes/get", {"supply_ids": supply_ids[i : i + 100]})
            for supply in result.get("supply") or []:
                cargoes[supply["supply_id"]] = supply.get("cargoes") or []
        return cargoes

    def prefetch_bundles(self, bundle_ids: list[str], workers: int = 4) -> None:
        """Параллельно загружает составы — по одному их ~0.7с на запрос, а грузомест тысячи."""
        todo = [b for b in dict.fromkeys(bundle_ids) if b not in self._bundle_cache]
        with concurrent.futures.ThreadPoolExecutor(workers) as pool:
            for bundle_id, items in zip(todo, pool.map(self._fetch_bundle_items, todo)):
                self._bundle_cache[bundle_id] = items

    def get_bundle_items(self, bundle_id: str) -> list[dict]:
        if bundle_id not in self._bundle_cache:
            self._bundle_cache[bundle_id] = self._fetch_bundle_items(bundle_id)
        return self._bundle_cache[bundle_id]

    def _fetch_bundle_items(self, bundle_id: str) -> list[dict]:
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


def cargo_quantities(
    api: OzonApi, cargoes: list[dict]
) -> tuple[dict[int, dict[str, int]], bool] | None:
    """SKU -> {"accepted", "lost", "pending"} по статусам грузомест и признак, что состав
    известен у всех грузомест; None, если грузомест нет."""
    if not cargoes:
        return None
    by_sku: dict[int, dict[str, int]] = {}
    complete = True
    for cargo in cargoes:
        status = (cargo.get("tracking_info") or {}).get("status")
        bucket = {CARGO_ACCEPTED: "accepted", CARGO_LOST: "lost"}.get(status, "pending")
        items = api.get_bundle_items(cargo["bundle_id"]) if cargo.get("bundle_id") else []
        if not items:
            complete = False
        for item in items:
            counts = by_sku.setdefault(item["sku"], {"accepted": 0, "lost": 0, "pending": 0})
            counts[bucket] += item.get("quantity") or 0
    return by_sku, complete


def build_rows(
    api: OzonApi, orders: list[dict], date_from: datetime.date, date_to: datetime.date
) -> list[dict]:
    in_period = []
    for order in orders:
        when = supply_date(order)
        if when is not None and date_from <= when.date() <= date_to:
            in_period.append((order, when))
    supply_ids = [
        supply["supply_id"]
        for order, _ in in_period
        for supply in order.get("supplies") or []
        if supply.get("supply_id")
    ]
    cargoes = api.get_cargoes(supply_ids)
    api.prefetch_bundles(
        [s["bundle_id"] for o, _ in in_period for s in o.get("supplies") or [] if s.get("bundle_id")]
        + [c["bundle_id"] for cs in cargoes.values() for c in cs if c.get("bundle_id")]
    )

    rows = []
    for order, when in in_period:
        created = parse_dt(order.get("created_date"))
        state = order.get("state", "")
        for supply in order.get("supplies") or []:
            bundle_id = supply.get("bundle_id")
            if not bundle_id:
                continue
            warehouse = (supply.get("storage_warehouse") or {}).get("name") or (
                order.get("drop_off_warehouse") or order.get("dropoff_warehouse") or {}
            ).get("name", "")
            by_cargo = cargo_quantities(api, cargoes.get(supply.get("supply_id"), []))
            for item in api.get_bundle_items(bundle_id):
                counts = None
                if by_cargo is not None:
                    by_sku, complete = by_cargo
                    counts = by_sku.get(item.get("sku"))
                    if counts is None and complete:
                        counts = {"accepted": 0, "lost": 0, "pending": 0}
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
                        "Принято, шт": counts["accepted"] if counts else "",
                        "Утеряно, шт": counts["lost"] if counts else "",
                        "На приёмке / в пути, шт": counts["pending"] if counts else "",
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

    def total(column: str) -> int:
        return sum(r[column] or 0 for r in rows)

    print(f"Строк за период: {len(rows)}")
    print(
        f"Отгружено: {total('Отгружено, шт')} шт, принято: {total('Принято, шт')} шт, "
        f"утеряно: {total('Утеряно, шт')} шт, на приёмке / в пути: "
        f"{total('На приёмке / в пути, шт')} шт"
    )
    print(f"Сохранено: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
