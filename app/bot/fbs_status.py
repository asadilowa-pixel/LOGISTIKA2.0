import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class FbsSnapshot:
    marketplace: str
    cabinet_id: int
    pending_count: int
    earliest_deadline: datetime.datetime | None


def ozon_order_deadlines(postings: list[dict]) -> dict[str, datetime.datetime]:
    deadlines = {}
    for posting in postings:
        shipment_date = posting.get("shipment_date")
        posting_number = posting.get("posting_number")
        if shipment_date and posting_number:
            deadlines[posting_number] = datetime.datetime.fromisoformat(shipment_date)
    return deadlines


def wb_order_deadlines(orders: list[dict], assembly_hours: float) -> dict[str, datetime.datetime]:
    # WB's orders/new response has no documented deadline field (see spec's "Открытые
    # вопросы") — approximated client-side as createdAt + assembly_hours.
    deadlines = {}
    for order in orders:
        created_at = order.get("createdAt")
        order_uid = order.get("orderUid")
        if created_at and order_uid:
            deadlines[order_uid] = datetime.datetime.fromisoformat(created_at) + datetime.timedelta(
                hours=assembly_hours
            )
    return deadlines


def summarize(
    marketplace: str, cabinet_id: int, deadlines: dict[str, datetime.datetime], pending_count: int
) -> FbsSnapshot:
    return FbsSnapshot(
        marketplace=marketplace,
        cabinet_id=cabinet_id,
        pending_count=pending_count,
        earliest_deadline=min(deadlines.values()) if deadlines else None,
    )


def format_status_message(snapshots: list[FbsSnapshot], now: datetime.datetime) -> str:
    lines = ["Статус ФБС-заказов:"]
    for snap in snapshots:
        label = f"{snap.marketplace} (кабинет {snap.cabinet_id})"
        if snap.pending_count == 0:
            lines.append(f"{label}: нет заказов к отгрузке")
            continue
        if snap.earliest_deadline is None:
            lines.append(f"{label}: к отгрузке {snap.pending_count}")
            continue
        hours_left = (snap.earliest_deadline - now).total_seconds() / 3600
        lines.append(
            f"{label}: к отгрузке {snap.pending_count}, ближайший дедлайн через {hours_left:.1f} ч"
        )
    return "\n".join(lines)


def orders_at_risk(
    deadlines: dict[str, datetime.datetime], now: datetime.datetime, threshold_hours: float
) -> dict[str, datetime.datetime]:
    cutoff = now + datetime.timedelta(hours=threshold_hours)
    return {key: deadline for key, deadline in deadlines.items() if deadline <= cutoff}
