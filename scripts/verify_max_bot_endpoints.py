"""Manual diagnostic script — run with real credentials to resolve the design spec's open
questions before trusting the Ozon/WB booking flows in production. Not part of the test
suite; prints raw API responses for a human to inspect.

Usage: python scripts/verify_max_bot_endpoints.py
Reads OZON_CABINET_1_* and WB_CABINET_1_* from .env via app.config.settings-style loading.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bot.cabinets import load_ozon_cabinets, load_wb_cabinets
from app.bot.ozon_client import OzonClient
from app.bot.wb_client import WbClient


def check_ozon_draft_visibility(client: OzonClient) -> None:
    print("=== Ozon: список черновиков поставки (проверить, видны ли черновики из ЛК) ===")
    postings = client.list_unfulfilled_postings(limit=5)
    print(json.dumps(postings[:2], indent=2, ensure_ascii=False))
    print(
        "Открытый вопрос #1 из спеки: создайте черновик вручную в ЛК Ozon, затем вручную "
        "вызовите client.get_draft_timeslots(<draft_id из ЛК>, ...) и сравните с ответом "
        "для черновика, созданного через client.create_draft(...). Если поля отличаются "
        "от того, что ожидает app/bot/booking_ozon.py, обновите ozon_client.py."
    )


def check_wb_coefficients_rate_limit(client: WbClient) -> None:
    print("=== WB: коэффициенты приёмки (проверить реальный лимит запросов) ===")
    warehouses = client.list_warehouses()
    print(f"Складов получено: {len(warehouses)}")
    sample_ids = [w["ID"] for w in warehouses[:3]]
    coefficients = client.get_acceptance_coefficients(sample_ids)
    print(json.dumps(coefficients[:3], indent=2, ensure_ascii=False))
    print(
        "Открытый вопрос #4 из спеки: сделайте 10 таких запросов подряд с интервалом 5с и "
        "проверьте, не появляется ли 429 — если да, увеличьте "
        "WB_COEFFICIENT_POLL_INTERVAL_MINUTES в .env."
    )


def check_wb_hidden_booking_method() -> None:
    print("=== WB: скрытый метод бронирования (открытый вопрос #3 из спеки) ===")
    print(
        "Не автоматизировано — откройте seller.wildberries.ru в браузере, откройте вкладку "
        "Network в DevTools, забронируйте один слот вручную и посмотрите, какой запрос "
        "фактически отправляется. Если это стабильный REST-вызов (не привязанный к "
        "сессионным cookie одноразового использования), запишите находку как правку к "
        "спеке — это может расширить scope позже, но не блокирует текущий план."
    )


def main() -> None:
    ozon_cabinets = load_ozon_cabinets()
    wb_cabinets = load_wb_cabinets()
    if not ozon_cabinets or not wb_cabinets:
        print("Заполните хотя бы один OZON_CABINET_* и WB_CABINET_* блок в .env перед запуском")
        sys.exit(1)

    check_ozon_draft_visibility(OzonClient(client_id=ozon_cabinets[0].client_id, api_key=ozon_cabinets[0].api_key))
    check_wb_coefficients_rate_limit(WbClient(token=wb_cabinets[0].token))
    check_wb_hidden_booking_method()


if __name__ == "__main__":
    main()
