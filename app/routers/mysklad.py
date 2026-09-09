from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends

from app.dependencies import get_ch_client
from app.models import MyskladOrderSupply, MyskladSupplyMarketplace
from app.repositories import fetch_mysklad_orders_supplies, fetch_mysklad_supplies_marketplaces

router = APIRouter(prefix="/mysklad", tags=["mysklad"])


@router.get("/orders-supplies", response_model=list[MyskladOrderSupply])
def orders_supplies(limit: int = 100, client: Client = Depends(get_ch_client)):
    return fetch_mysklad_orders_supplies(client, limit=limit)


@router.get("/supplies-marketplaces", response_model=list[MyskladSupplyMarketplace])
def supplies_marketplaces(limit: int = 100, client: Client = Depends(get_ch_client)):
    return fetch_mysklad_supplies_marketplaces(client, limit=limit)
