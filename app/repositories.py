from clickhouse_connect.driver.client import Client

from app.models import (
    MyskladOrderSupply,
    MyskladSupplyMarketplace,
    OzonStockFbo,
    OzonStockFbs,
    UnifiedStock,
    WatchdogFreshness,
    WatchdogRun,
    WbStockFbo,
    WbStockFbs,
)


def _rows_as(cls, client: Client, query: str):
    result = client.query(query)
    return [cls(**dict(zip(result.column_names, row))) for row in result.result_rows]


def fetch_ozon_stocks_fbo(client: Client) -> list[OzonStockFbo]:
    return _rows_as(OzonStockFbo, client, "SELECT * FROM ozon.stocks_fbo")


def fetch_ozon_stocks_fbs(client: Client) -> list[OzonStockFbs]:
    return _rows_as(OzonStockFbs, client, "SELECT * FROM ozon.stocks_fbs")


def fetch_wb_stocks_fbo(client: Client) -> list[WbStockFbo]:
    return _rows_as(WbStockFbo, client, "SELECT * FROM wildberies.stocks_fbo")


def fetch_wb_stocks_fbs(client: Client) -> list[WbStockFbs]:
    return _rows_as(WbStockFbs, client, "SELECT * FROM wildberies.stocks_fbs")


def fetch_unified_stocks(client: Client) -> list[UnifiedStock]:
    unified = []

    for row in fetch_ozon_stocks_fbo(client):
        unified.append(
            UnifiedStock(
                marketplace="ozon",
                fulfillment="fbo",
                article_seller=row.article_seller,
                warehouse=row.sklad_name,
                quantity=row.stocks,
                cabinet=row.name_cabinet,
                id_client=row.id_client,
                id_cabinet=row.id_cabinet,
            )
        )

    for row in fetch_ozon_stocks_fbs(client):
        unified.append(
            UnifiedStock(
                marketplace="ozon",
                fulfillment="fbs",
                article_seller=row.article_seller,
                warehouse=row.sklad_name,
                quantity=row.stocks,
                cabinet=row.name_cabinet,
                id_client=row.id_client,
                id_cabinet=row.id_cabinet,
            )
        )

    for row in fetch_wb_stocks_fbo(client):
        unified.append(
            UnifiedStock(
                marketplace="wb",
                fulfillment="fbo",
                article_seller=row.article_seller,
                warehouse=row.sklad,
                quantity=row.stocks_current_day or 0,  # Nullable in source
                cabinet=row.name_cabinet,
                id_client=row.id_client,
                id_cabinet=row.id_cabinet,
            )
        )

    for row in fetch_wb_stocks_fbs(client):
        unified.append(
            UnifiedStock(
                marketplace="wb",
                fulfillment="fbs",
                article_seller=row.article_seller,
                warehouse=row.sklad,
                quantity=row.stocks,
                cabinet=row.cabinet_name,
                id_client=row.id_client,
                id_cabinet=row.id_cabinet,
            )
        )

    return unified


def fetch_mysklad_orders_supplies(client: Client, limit: int = 100) -> list[MyskladOrderSupply]:
    return _rows_as(
        MyskladOrderSupply,
        client,
        f"SELECT * FROM mysklad.orders_supplies ORDER BY moment DESC LIMIT {limit}",
    )


def fetch_mysklad_supplies_marketplaces(client: Client, limit: int = 100) -> list[MyskladSupplyMarketplace]:
    return _rows_as(
        MyskladSupplyMarketplace,
        client,
        f"SELECT * FROM mysklad.supplies_marketplaces ORDER BY moment DESC LIMIT {limit}",
    )


def fetch_watchdog_freshness(client: Client, limit: int = 100) -> list[WatchdogFreshness]:
    return _rows_as(
        WatchdogFreshness,
        client,
        f"SELECT * FROM watchdog.freshness ORDER BY checked_at DESC LIMIT {limit}",
    )


def fetch_watchdog_runs(client: Client, limit: int = 100) -> list[WatchdogRun]:
    return _rows_as(
        WatchdogRun,
        client,
        f"SELECT * FROM watchdog.runs ORDER BY started_at DESC LIMIT {limit}",
    )
