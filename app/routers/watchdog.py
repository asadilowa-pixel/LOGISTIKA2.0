from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends

from app.dependencies import get_ch_client
from app.models import WatchdogFreshness, WatchdogRun
from app.repositories import fetch_watchdog_freshness, fetch_watchdog_runs

router = APIRouter(prefix="/watchdog", tags=["watchdog"])


@router.get("/freshness", response_model=list[WatchdogFreshness])
def freshness(limit: int = 100, client: Client = Depends(get_ch_client)):
    return fetch_watchdog_freshness(client, limit=limit)


@router.get("/runs", response_model=list[WatchdogRun])
def runs(limit: int = 100, client: Client = Depends(get_ch_client)):
    return fetch_watchdog_runs(client, limit=limit)
