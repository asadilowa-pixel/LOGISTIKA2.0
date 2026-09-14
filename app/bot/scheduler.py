import datetime
import sqlite3

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot import state
from app.bot.alert_jobs import check_fbs_deadlines
from app.bot.booking_ozon import poll_draft_watch
from app.bot.fbs_status import ozon_order_deadlines, wb_order_deadlines
from app.bot.watch_wb import poll_coefficient_watch


def poll_all_watches(
    ozon_clients: dict[int, object],
    wb_clients: dict[int, object],
    conn: sqlite3.Connection,
    now: str,
    cooldown_minutes: float,
) -> list[str]:
    messages = []
    for row in state.list_watch_requests(conn, status="watching"):
        if row["marketplace"] == "ozon":
            client = ozon_clients.get(row["cabinet_id"])
            if client is None:
                continue
            message = poll_draft_watch(client, conn, row, now)
        else:
            client = wb_clients.get(row["cabinet_id"])
            if client is None:
                continue
            message = poll_coefficient_watch(client, conn, row, now, cooldown_minutes)
        if message is not None:
            messages.append(message)
    return messages


def sweep_expired_watches(conn: sqlite3.Connection, now: str) -> list[int]:
    expired_ids = []
    for row in state.list_watch_requests(conn, status="watching"):
        if row["date_to"] < now[:10]:
            state.update_watch_status(conn, row["id"], "expired", now)
            expired_ids.append(row["id"])
    return expired_ids


def build_scheduler(
    *,
    ozon_clients: dict[int, object],
    wb_clients: dict[int, object],
    conn: sqlite3.Connection,
    telegram_client,
    chat_ids: set[int],
    watch_poll_seconds: int,
    fbs_poll_minutes: int,
    cooldown_minutes: float,
    now_fn,
    alert_hours_before_deadline: float,
    wb_assembly_hours: float,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    def _poll_watches_job():
        messages = poll_all_watches(ozon_clients, wb_clients, conn, now_fn().isoformat(), cooldown_minutes)
        messages.extend(f"Наблюдение истекло: watch {wid}" for wid in sweep_expired_watches(conn, now_fn().isoformat()))
        for message in messages:
            for chat_id in chat_ids:
                telegram_client.send_message(chat_id, message)

    def _check_fbs_job():
        now = datetime.datetime.now(datetime.timezone.utc)
        messages = []
        for cabinet_id, client in ozon_clients.items():
            deadlines = ozon_order_deadlines(client.list_unfulfilled_postings())
            messages.extend(check_fbs_deadlines(
                conn, marketplace="ozon", cabinet_id=cabinet_id, deadlines=deadlines,
                now=now, threshold_hours=alert_hours_before_deadline,
            ))
        for cabinet_id, client in wb_clients.items():
            deadlines = wb_order_deadlines(client.list_new_orders(), assembly_hours=wb_assembly_hours)
            messages.extend(check_fbs_deadlines(
                conn, marketplace="wb", cabinet_id=cabinet_id, deadlines=deadlines,
                now=now, threshold_hours=alert_hours_before_deadline,
            ))
        for message in messages:
            for chat_id in chat_ids:
                telegram_client.send_message(chat_id, message)

    scheduler.add_job(_poll_watches_job, "interval", seconds=watch_poll_seconds, id="poll_watches")
    scheduler.add_job(_check_fbs_job, "interval", minutes=fbs_poll_minutes, id="check_fbs_deadlines")
    return scheduler
