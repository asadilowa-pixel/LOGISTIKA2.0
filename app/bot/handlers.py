import datetime
import sqlite3

from app.bot import state
from app.bot.fbs_status import (
    format_status_message,
    ozon_order_deadlines,
    summarize,
    wb_order_deadlines,
)


def parse_update(update: dict) -> dict | None:
    if "message" in update:
        message = update["message"]
        text = (message.get("text") or "").strip()
        return {"kind": "command", "chat_id": message["chat"]["id"], "text": text}

    if "callback_query" in update:
        callback = update["callback_query"]
        message = callback.get("message") or {}
        return {
            "kind": "callback",
            "chat_id": (message.get("chat") or {}).get("id"),
            "callback_id": callback["id"],
            "payload": callback.get("data", ""),
        }

    return None


def handle_status_command(
    telegram_client,
    *,
    chat_id: int,
    cabinets_data: list[tuple[str, int, list[dict]]],
    now: datetime.datetime,
    wb_assembly_hours: float = 48.0,
) -> None:
    snapshots = []
    for marketplace, cabinet_id, raw_items in cabinets_data:
        if marketplace == "ozon":
            deadlines = ozon_order_deadlines(raw_items)
        else:
            deadlines = wb_order_deadlines(raw_items, assembly_hours=wb_assembly_hours)
        snapshots.append(summarize(marketplace, cabinet_id, deadlines, pending_count=len(raw_items)))

    telegram_client.send_message(chat_id, format_status_message(snapshots, now))


def handle_cancel_command(conn: sqlite3.Connection, *, chat_id: int, args: list[str], now: str) -> str:
    if not args or not args[0].isdigit():
        return "Использование: /cancel <номер наблюдения>"
    watch_id = int(args[0])
    matching = [
        row for row in state.list_watch_requests(conn, status="watching") if row["id"] == watch_id
    ]
    if not matching:
        return f"Наблюдение {watch_id} не найдено среди активных"
    state.update_watch_status(conn, watch_id, "cancelled", now=now)
    return f"Наблюдение {watch_id} отменено"


MAIN_MENU_BUTTONS = [
    [{"text": "📊 Статус", "callback_data": "menu:status"}],
    [{"text": "❌ Отменить наблюдение", "callback_data": "menu:cancel_list"}],
]


def handle_menu_command(telegram_client, *, chat_id: int) -> None:
    telegram_client.send_message(chat_id, "Выберите действие:", buttons=MAIN_MENU_BUTTONS)


def handle_cancel_list_callback(telegram_client, conn: sqlite3.Connection, *, chat_id: int) -> None:
    watches = state.list_watch_requests(conn, status="watching")
    if not watches:
        telegram_client.send_message(chat_id, "Нет активных наблюдений")
        return
    buttons = [
        [{
            "text": f"#{row['id']} {row['marketplace']} кабинет {row['cabinet_id']} "
                    f"({row['date_from']} — {row['date_to']})",
            "callback_data": f"cancel:{row['id']}",
        }]
        for row in watches
    ]
    telegram_client.send_message(chat_id, "Выберите наблюдение для отмены:", buttons=buttons)
