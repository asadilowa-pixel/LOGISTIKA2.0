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


def _rows_as(cls, client: Client, query: str, parameters: dict | None = None):
    result = client.query(query, parameters=parameters)
    return [cls(**dict(zip(result.column_names, row))) for row in result.result_rows]


def _where_clause(filters: dict[str, tuple[object, str]]) -> tuple[str, dict]:
    """filters: {column: (value, clickhouse_type)}; columns with a None value
    are left out of the query entirely."""
    conditions = []
    params = {}
    for column, (value, ch_type) in filters.items():
        if value is not None:
            conditions.append(f"{column} = {{{column}:{ch_type}}}")
            params[column] = value
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    return where, params


def fetch_ozon_stocks_fbo(client: Client, id_client: int | None = None) -> list[OzonStockFbo]:
    where, params = _where_clause({"id_client": (id_client, "UInt8")})
    return _rows_as(OzonStockFbo, client, f"SELECT * FROM ozon.stocks_fbo{where}", params)


def fetch_ozon_stocks_fbs(client: Client, id_client: int | None = None) -> list[OzonStockFbs]:
    where, params = _where_clause({"id_client": (id_client, "UInt8")})
    return _rows_as(OzonStockFbs, client, f"SELECT * FROM ozon.stocks_fbs{where}", params)


def fetch_wb_stocks_fbo(client: Client, id_client: int | None = None) -> list[WbStockFbo]:
    where, params = _where_clause({"id_client": (id_client, "UInt8")})
    return _rows_as(WbStockFbo, client, f"SELECT * FROM wildberies.stocks_fbo{where}", params)


def fetch_wb_stocks_fbs(client: Client, id_client: int | None = None) -> list[WbStockFbs]:
    where, params = _where_clause({"id_client": (id_client, "UInt8")})
    return _rows_as(WbStockFbs, client, f"SELECT * FROM wildberies.stocks_fbs{where}", params)


def fetch_unified_stocks(
    client: Client, id_client: int | None = None, marketplace: str | None = None
) -> list[UnifiedStock]:
    unified = []

    if marketplace in (None, "ozon"):
        for row in fetch_ozon_stocks_fbo(client, id_client=id_client):
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

        for row in fetch_ozon_stocks_fbs(client, id_client=id_client):
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

    if marketplace in (None, "wb"):
        for row in fetch_wb_stocks_fbo(client, id_client=id_client):
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

        for row in fetch_wb_stocks_fbs(client, id_client=id_client):
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


def fetch_mysklad_orders_supplies(
    client: Client, limit: int = 100, id_client: int | None = None
) -> list[MyskladOrderSupply]:
    where, params = _where_clause({"id_client": (id_client, "UInt8")})
    query = f"SELECT * FROM mysklad.orders_supplies{where} ORDER BY moment DESC LIMIT {limit}"
    return _rows_as(MyskladOrderSupply, client, query, params)


def fetch_mysklad_supplies_marketplaces(
    client: Client, limit: int = 100, id_client: int | None = None, marketplace: str | None = None
) -> list[MyskladSupplyMarketplace]:
    where, params = _where_clause(
        {"id_client": (id_client, "UInt8"), "marketplace": (marketplace, "String")}
    )
    query = f"SELECT * FROM mysklad.supplies_marketplaces{where} ORDER BY moment DESC LIMIT {limit}"
    return _rows_as(MyskladSupplyMarketplace, client, query, params)


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
