from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_ch_client
from app.models import OzonStockFbo, OzonStockFbs, UnifiedStock, WbStockFbo, WbStockFbs
from app.repositories import (
    fetch_ozon_stocks_fbo,
    fetch_ozon_stocks_fbs,
    fetch_unified_stocks,
    fetch_wb_stocks_fbo,
    fetch_wb_stocks_fbs,
)

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/unified", response_model=list[UnifiedStock])
def unified(
    id_client: int | None = None,
    marketplace: str | None = None,
    client: Client = Depends(get_ch_client),
):
    if marketplace is not None and marketplace not in ("ozon", "wb"):
        raise HTTPException(status_code=400, detail="marketplace must be 'ozon' or 'wb'")
    return fetch_unified_stocks(client, id_client=id_client, marketplace=marketplace)


@router.get("/ozon/fbo", response_model=list[OzonStockFbo])
def ozon_fbo(id_client: int | None = None, client: Client = Depends(get_ch_client)):
    return fetch_ozon_stocks_fbo(client, id_client=id_client)


@router.get("/ozon/fbs", response_model=list[OzonStockFbs])
def ozon_fbs(id_client: int | None = None, client: Client = Depends(get_ch_client)):
    return fetch_ozon_stocks_fbs(client, id_client=id_client)


@router.get("/wb/fbo", response_model=list[WbStockFbo])
def wb_fbo(id_client: int | None = None, client: Client = Depends(get_ch_client)):
    return fetch_wb_stocks_fbo(client, id_client=id_client)


@router.get("/wb/fbs", response_model=list[WbStockFbs])
def wb_fbs(id_client: int | None = None, client: Client = Depends(get_ch_client)):
    return fetch_wb_stocks_fbs(client, id_client=id_client)
