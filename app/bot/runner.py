import asyncio
import datetime
import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

from app.bot.handlers import (
    handle_cancel_command,
    handle_cancel_list_callback,
    handle_menu_command,
    handle_status_command,
    parse_update,
)
from app.bot.telegram_client import TelegramClient


def poll_once(
    telegram_client: TelegramClient,
    *,
    offset: int | None,
    on_command: Callable[[int, str], None],
    on_callback: Callable[[int | None, str, str], None],
) -> int | None:
    response = telegram_client.get_updates(offset=offset)
    new_offset = offset
    for update in response.get("result", []):
        new_offset = update["update_id"] + 1
        parsed = parse_update(update)
        if parsed is None:
            continue
        if parsed["kind"] == "command":
            on_command(parsed["chat_id"], parsed["text"])
        elif parsed["kind"] == "callback":
            on_callback(parsed["chat_id"], parsed["callback_id"], parsed["payload"])
    return new_offset


@dataclass
class BotContext:
    telegram_client: TelegramClient
    conn: object
    ozon_clients: dict
    wb_clients: dict
    allowed_chat_ids: set[int]
    scheduler: object


def _send_status(context: BotContext, chat_id: int) -> None:
    cabinets_data = [
        ("ozon", cid, client.list_unfulfilled_postings())
        for cid, client in context.ozon_clients.items()
    ] + [
        ("wb", cid, client.list_new_orders())
        for cid, client in context.wb_clients.items()
    ]
    handle_status_command(
        context.telegram_client, chat_id=chat_id, cabinets_data=cabinets_data,
        now=datetime.datetime.now(datetime.timezone.utc),
    )


def dispatch_command(context: BotContext, chat_id: int, text: str) -> None:
    if chat_id not in context.allowed_chat_ids:
        return
    if text == "/status":
        _send_status(context, chat_id)
    elif text in ("/start", "/menu"):
        handle_menu_command(context.telegram_client, chat_id=chat_id)
    elif text.startswith("/cancel"):
        reply = handle_cancel_command(
            context.conn, chat_id=chat_id, args=text.split()[1:],
            now=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        context.telegram_client.send_message(chat_id, reply)


def dispatch_callback(context: BotContext, chat_id: int | None, callback_id: str, payload: str) -> None:
    if chat_id not in context.allowed_chat_ids:
        return
    if payload == "menu:status":
        _send_status(context, chat_id)
        context.telegram_client.answer_callback(callback_id)
    elif payload == "menu:cancel_list":
        handle_cancel_list_callback(context.telegram_client, context.conn, chat_id=chat_id)
        context.telegram_client.answer_callback(callback_id)
    elif payload.startswith("cancel:"):
        watch_id = payload.split(":", 1)[1]
        reply = handle_cancel_command(
            context.conn, chat_id=chat_id, args=[watch_id],
            now=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        context.telegram_client.answer_callback(callback_id, text=reply)
    else:
        context.telegram_client.answer_callback(callback_id)


def build_context(settings) -> BotContext:
    from app.bot import state
    from app.bot.cabinets import load_ozon_cabinets, load_wb_cabinets
    from app.bot.ozon_client import OzonClient
    from app.bot.wb_client import WbClient
    from app.bot.scheduler import build_scheduler

    conn = state.connect("bot_state.db")
    telegram_client = TelegramClient(token=settings.telegram_bot_token)
    ozon_clients = {
        c.cabinet_id: OzonClient(client_id=c.client_id, api_key=c.api_key)
        for c in load_ozon_cabinets()
    }
    wb_clients = {c.cabinet_id: WbClient(token=c.token) for c in load_wb_cabinets()}
    allowed_chat_ids = {
        int(cid.strip())
        for cid in settings.telegram_allowed_chat_ids.split(",")
        if cid.strip()
    }
    scheduler = build_scheduler(
        ozon_clients=ozon_clients,
        wb_clients=wb_clients,
        conn=conn,
        telegram_client=telegram_client,
        chat_ids=allowed_chat_ids,
        watch_poll_seconds=settings.ozon_watch_poll_interval_seconds,
        fbs_poll_minutes=settings.fbs_poll_interval_minutes,
        cooldown_minutes=settings.wb_coefficient_alert_cooldown_minutes,
        now_fn=datetime.datetime.now,
        alert_hours_before_deadline=settings.alert_hours_before_deadline,
        wb_assembly_hours=settings.wb_assembly_hours,
    )
    return BotContext(
        telegram_client=telegram_client, conn=conn, ozon_clients=ozon_clients,
        wb_clients=wb_clients, allowed_chat_ids=allowed_chat_ids, scheduler=scheduler,
    )


async def run_forever(context: BotContext) -> None:
    context.scheduler.start()
    offset = None
    try:
        while True:
            try:
                offset = await asyncio.to_thread(
                    poll_once, context.telegram_client, offset=offset,
                    on_command=lambda chat_id, text: dispatch_command(context, chat_id, text),
                    on_callback=lambda chat_id, cb_id, payload: dispatch_callback(
                        context, chat_id, cb_id, payload
                    ),
                )
            except Exception:
                logger.exception("Bot polling iteration failed; continuing")
    finally:
        context.scheduler.shutdown(wait=False)
