from clickhouse_connect.driver.client import Client

from app.models import (
    OzonStockFbo,
    OzonStockFbs,
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
