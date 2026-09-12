import datetime
import sqlite3

from app.bot import state
from app.bot.fbs_status import orders_at_risk


def check_fbs_deadlines(
    conn: sqlite3.Connection,
    *,
    marketplace: str,
    cabinet_id: int,
    deadlines: dict[str, datetime.datetime],
    now: datetime.datetime,
    threshold_hours: float,
) -> list[str]:
    at_risk = orders_at_risk(deadlines, now, threshold_hours)
    messages = []
    for order_key, deadline in at_risk.items():
        is_new = state.record_alert(
            conn,
            marketplace=marketplace,
            cabinet_id=cabinet_id,
            order_key=order_key,
            alert_type="deadline_risk",
            now=now.isoformat(),
        )
        if not is_new:
            continue
        hours_left = (deadline - now).total_seconds() / 3600
        messages.append(
            f"⚠ {marketplace} (кабинет {cabinet_id}): заказ {order_key} — "
            f"до дедлайна {hours_left:.1f} ч, риск не успеть в доставку"
        )
    return messages
