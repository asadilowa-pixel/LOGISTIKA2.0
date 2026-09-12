import datetime
from pathlib import Path

from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.dependencies import get_ch_client
from app.models import FbsOrderCount, LogisticsExpenses
from app.repositories import fetch_fbs_order_count, fetch_logistics_expenses

router = APIRouter(tags=["dashboard"])

DASHBOARD_HTML = Path(__file__).resolve().parent.parent / "static" / "dashboard.html"


@router.get("/", include_in_schema=False)
def dashboard_page():
    return FileResponse(DASHBOARD_HTML)


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
