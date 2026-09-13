import datetime
import json
import sqlite3

from app.bot import state


def start_coefficient_watch(
    conn: sqlite3.Connection,
    *,
    cabinet_id: int,
    warehouse_id: int,
    date_from: str,
    date_to: str,
    max_coefficient: int,
    chat_id: int,
    now: str,
) -> int:
    return state.create_watch_request(
        conn,
        marketplace="wb",
        cabinet_id=cabinet_id,
        kind="wb_coefficient",
        reference_json=json.dumps({"warehouse_id": warehouse_id}),
        date_from=date_from,
        date_to=date_to,
        max_coefficient=max_coefficient,
        requested_by_chat_id=chat_id,
        now=now,
    )


def poll_coefficient_watch(
    wb_client, conn: sqlite3.Connection, watch_row, now: str, cooldown_minutes: float
) -> str | None:
    reference = json.loads(watch_row["reference_json"])
    warehouse_id = reference["warehouse_id"]
    date_from = watch_row["date_from"]
    date_to = watch_row["date_to"]
    max_coefficient = watch_row["max_coefficient"]

    coefficients = wb_client.get_acceptance_coefficients([warehouse_id])
    for entry in coefficients:
        if entry["warehouseID"] != warehouse_id:
            continue
        if entry["coefficient"] > max_coefficient:
            continue
        entry_date = entry["date"][:10]
        if not (date_from <= entry_date <= date_to):
            continue

        order_key = f"{warehouse_id}:{entry_date}"
        cooldown_cutoff = (
            datetime.datetime.fromisoformat(now)
            - datetime.timedelta(minutes=cooldown_minutes)
        ).isoformat()
        conn.execute(
            "DELETE FROM alert_log WHERE marketplace = 'wb' AND cabinet_id = ? AND order_key = ? "
            "AND alert_type = 'coefficient_available' AND sent_at < ?",
            (watch_row["cabinet_id"], order_key, cooldown_cutoff),
        )
        conn.commit()

        is_new = state.record_alert(
            conn,
            marketplace="wb",
            cabinet_id=watch_row["cabinet_id"],
            order_key=order_key,
            alert_type="coefficient_available",
            now=now,
        )
        if not is_new:
            return None
        return (
            f"Появился слот на складе {warehouse_id} ({entry_date}), "
            f"коэффициент {entry['coefficient']} — забронируйте в личном кабинете"
        )
    return None
