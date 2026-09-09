import datetime

from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_ch_client
from app.models import FbsOrderCount, LogisticsExpenses
from app.repositories import fetch_fbs_order_count, fetch_logistics_expenses

router = APIRouter(tags=["dashboard"])


def _validate_range(date_from: datetime.date, date_to: datetime.date) -> None:
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be <= date_to")


@router.get("/expenses/logistics", response_model=LogisticsExpenses)
def expenses_logistics(
    date_from: datetime.date,
    date_to: datetime.date,
    id_client: int | None = None,
    client: Client = Depends(get_ch_client),
):
    _validate_range(date_from, date_to)
    return fetch_logistics_expenses(client, date_from=date_from, date_to=date_to, id_client=id_client)


@router.get("/orders/fbs-count", response_model=FbsOrderCount)
def orders_fbs_count(
    date_from: datetime.date,
    date_to: datetime.date,
    id_client: int | None = None,
    client: Client = Depends(get_ch_client),
):
    _validate_range(date_from, date_to)
    return fetch_fbs_order_count(client, date_from=date_from, date_to=date_to, id_client=id_client)
