import datetime

from app.bot.fbs_status import (
    format_status_message,
    ozon_order_deadlines,
    summarize,
    wb_order_deadlines,
)


def parse_update(update: dict) -> dict | None:
    update_type = update.get("update_type")

    if update_type == "message_created":
        message = update["message"]
        text = ((message.get("body") or {}).get("text") or "").strip()
        return {"kind": "command", "chat_id": message["recipient"]["chat_id"], "text": text}

    if update_type == "message_callback":
        callback = update["callback"]
        message = update.get("message") or {}
        return {
            "kind": "callback",
            "chat_id": (message.get("recipient") or {}).get("chat_id"),
            "callback_id": callback["callback_id"],
            "payload": callback.get("payload", ""),
        }

    return None


def handle_status_command(
    max_client,
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

    max_client.send_message(chat_id, format_status_message(snapshots, now))
