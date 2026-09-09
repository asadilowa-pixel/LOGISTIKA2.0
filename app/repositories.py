import datetime

from clickhouse_connect.driver.client import Client

from app.models import (
    FbsOrderCount,
    LogisticsExpenses,
    MyskladOrderSupply,
    MyskladSupplyMarketplace,
    OzonLogisticsExpenses,
    OzonStockFbo,
    OzonStockFbs,
    UnifiedStock,
    WatchdogFreshness,
    WatchdogRun,
    WbLogisticsExpenses,
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


def fetch_logistics_expenses(
    client: Client,
    date_from: datetime.date,
    date_to: datetime.date,
    id_client: int | None = None,
) -> LogisticsExpenses:
    ozon_conditions = ["date_operation BETWEEN {date_from:Date} AND {date_to:Date}"]
    ozon_params = {"date_from": date_from, "date_to": date_to}
    if id_client is not None:
        ozon_conditions.append("id_client = {id_client:UInt8}")
        ozon_params["id_client"] = id_client
    ozon_where = " AND ".join(ozon_conditions)

    ozon_count = client.query(
        f"SELECT count() FROM ozon.expenses_agg WHERE {ozon_where}", parameters=ozon_params
    ).result_rows[0][0]

    if ozon_count == 0:
        ozon = None
    else:
        logistics_cost, returned_logistics_cost, last_mile_cost, cancel_last_mile_cost = (
            float(v)
            for v in client.query(
                f"""SELECT sum(logistick_cost), sum(returned_logistick_cost),
                           sum(last_mile_cost), sum(cancel_last_mile_cost)
                    FROM ozon.expenses_agg WHERE {ozon_where}""",
                parameters=ozon_params,
            ).result_rows[0]
        )
        ozon = OzonLogisticsExpenses(
            logistics_cost=logistics_cost,
            returned_logistics_cost=returned_logistics_cost,
            last_mile_cost=last_mile_cost,
            cancel_last_mile_cost=cancel_last_mile_cost,
            total=logistics_cost + returned_logistics_cost + last_mile_cost + cancel_last_mile_cost,
        )

    # wildberies.logistics_costs has no id_client column — date range only.
    wb_where = "date BETWEEN {date_from:Date} AND {date_to:Date}"
    wb_params = {"date_from": date_from, "date_to": date_to}

    wb_count = client.query(
        f"SELECT count() FROM wildberies.logistics_costs WHERE {wb_where}", parameters=wb_params
    ).result_rows[0][0]

    if wb_count == 0:
        wb = None
    else:
        wb_logistics_cost, wb_reverse_logistics_cost = (
            float(v)
            for v in client.query(
                f"""SELECT sum(logistics_cost), sum(reverse_logistics_cost)
                    FROM wildberies.logistics_costs WHERE {wb_where}""",
                parameters=wb_params,
            ).result_rows[0]
        )
        wb = WbLogisticsExpenses(
            logistics_cost=wb_logistics_cost,
            reverse_logistics_cost=wb_reverse_logistics_cost,
            total=wb_logistics_cost + wb_reverse_logistics_cost,
        )

    return LogisticsExpenses(date_from=date_from, date_to=date_to, ozon=ozon, wb=wb)


def fetch_fbs_order_count(
    client: Client,
    date_from: datetime.date,
    date_to: datetime.date,
    id_client: int | None = None,
) -> FbsOrderCount:
    ozon_conditions = ["in_process_at BETWEEN {date_from:Date} AND {date_to:Date}"]
    ozon_params = {"date_from": date_from, "date_to": date_to}
    if id_client is not None:
        ozon_conditions.append("id_client = {id_client:UInt8}")
        ozon_params["id_client"] = id_client
    ozon_where = " AND ".join(ozon_conditions)

    ozon_count = client.query(
        f"SELECT count() FROM ozon.ozon_fbs_postings WHERE {ozon_where}", parameters=ozon_params
    ).result_rows[0][0]

    wb_conditions = ["fbs = true", "date BETWEEN {date_from:Date} AND {date_to:Date}"]
    wb_params = {"date_from": date_from, "date_to": date_to}
    if id_client is not None:
        wb_conditions.append("id_client = {id_client:UInt8}")
        wb_params["id_client"] = id_client
    wb_where = " AND ".join(wb_conditions)

    wb_count = client.query(
        f"SELECT count() FROM wildberies.orders WHERE {wb_where}", parameters=wb_params
    ).result_rows[0][0]

    return FbsOrderCount(date_from=date_from, date_to=date_to, ozon=ozon_count, wb=wb_count)
