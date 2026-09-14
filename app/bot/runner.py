import asyncio
import datetime
from dataclasses import dataclass
from typing import Callable

from app.bot.handlers import parse_update
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
    chat_id: int
    scheduler: object


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
    scheduler = build_scheduler(
        ozon_clients=ozon_clients,
        wb_clients=wb_clients,
        conn=conn,
        telegram_client=telegram_client,
        chat_id=settings.telegram_chat_id,
        watch_poll_seconds=settings.ozon_watch_poll_interval_seconds,
        fbs_poll_minutes=settings.fbs_poll_interval_minutes,
        cooldown_minutes=settings.wb_coefficient_alert_cooldown_minutes,
        now_fn=datetime.datetime.now,
        alert_hours_before_deadline=settings.alert_hours_before_deadline,
        wb_assembly_hours=settings.wb_assembly_hours,
    )
    return BotContext(
        telegram_client=telegram_client, conn=conn, ozon_clients=ozon_clients,
        wb_clients=wb_clients, chat_id=settings.telegram_chat_id, scheduler=scheduler,
    )


async def run_forever(context: BotContext) -> None:
    from app.bot.handlers import handle_cancel_command, handle_status_command

    context.scheduler.start()
    offset = None
    try:
        while True:
            def on_command(chat_id, text):
                if chat_id != context.chat_id:
                    return
                if text == "/status":
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
                elif text.startswith("/cancel"):
                    reply = handle_cancel_command(
                        context.conn, chat_id=chat_id, args=text.split()[1:],
                        now=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    )
                    context.telegram_client.send_message(chat_id, reply)

            def on_callback(chat_id, callback_id, payload):
                if chat_id != context.chat_id:
                    return
                context.telegram_client.answer_callback(callback_id, text="Принято")

            offset = await asyncio.to_thread(
                poll_once, context.telegram_client, offset=offset,
                on_command=on_command, on_callback=on_callback,
            )
    finally:
        context.scheduler.shutdown(wait=False)
