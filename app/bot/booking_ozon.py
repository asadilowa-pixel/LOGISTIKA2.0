import json
import sqlite3

from app.bot import state


def _pick_free_slot(timeslots: list[dict], max_coefficient: int) -> dict | None:
    candidates = [t for t in timeslots if t["coefficient"] <= max_coefficient]
    return candidates[0] if candidates else None


def _cheapest_paid_slot(timeslots: list[dict]) -> dict | None:
    paid = [t for t in timeslots if t["coefficient"] > 0]
    return min(paid, key=lambda t: t["coefficient"]) if paid else None


def start_draft_booking(
    ozon_client,
    conn: sqlite3.Connection,
    *,
    cabinet_id: int,
    items: list[dict],
    warehouse_ids: list[int],
    date_from: str,
    date_to: str,
    chat_id: int,
    now: str,
) -> dict:
    operation_id = ozon_client.create_draft(items, warehouse_ids)
    draft_id = ozon_client.get_draft_id(operation_id)
    timeslots = ozon_client.get_draft_timeslots(draft_id, date_from, date_to) if draft_id else []

    free_slot = _pick_free_slot(timeslots, max_coefficient=0)
    if free_slot is not None:
        ozon_client.book_draft_timeslot(draft_id, free_slot["timeslot"])
        return {
            "outcome": "booked",
            "message": f"Забронирован бесплатный слот {free_slot['date']} (склад {free_slot['warehouse_id']})",
        }

    paid_slot = _cheapest_paid_slot(timeslots)
    if paid_slot is not None:
        return {
            "outcome": "awaiting_confirmation",
            "message": f"Найден платный слот {paid_slot['date']} (коэффициент {paid_slot['coefficient']}) — нужно подтверждение",
            "draft_id": draft_id,
            "timeslot": paid_slot["timeslot"],
        }

    watch_id = state.create_watch_request(
        conn,
        marketplace="ozon",
        cabinet_id=cabinet_id,
        kind="ozon_draft_create",
        reference_json=json.dumps({"draft_id": draft_id}),
        date_from=date_from,
        date_to=date_to,
        max_coefficient=0,
        requested_by_chat_id=chat_id,
        now=now,
    )
    return {
        "outcome": "watching",
        "message": "Свободных слотов пока нет, продолжаю наблюдение",
        "watch_id": watch_id,
    }


def poll_draft_watch(ozon_client, conn: sqlite3.Connection, watch_row, now: str) -> str | None:
    reference = json.loads(watch_row["reference_json"])
    draft_id = reference["draft_id"]

    timeslots = ozon_client.get_draft_timeslots(
        draft_id, watch_row["date_from"], watch_row["date_to"]
    )
    free_slot = _pick_free_slot(timeslots, max_coefficient=watch_row["max_coefficient"])
    if free_slot is None:
        return None

    ozon_client.book_draft_timeslot(draft_id, free_slot["timeslot"])
    state.update_watch_status(conn, watch_row["id"], "booked", now)
    return f"Забронирован бесплатный слот {free_slot['date']} (склад {free_slot['warehouse_id']})"
