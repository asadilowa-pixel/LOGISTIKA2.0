from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends

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
def unified(client: Client = Depends(get_ch_client)):
    return fetch_unified_stocks(client)


@router.get("/ozon/fbo", response_model=list[OzonStockFbo])
def ozon_fbo(client: Client = Depends(get_ch_client)):
    return fetch_ozon_stocks_fbo(client)


@router.get("/ozon/fbs", response_model=list[OzonStockFbs])
def ozon_fbs(client: Client = Depends(get_ch_client)):
    return fetch_ozon_stocks_fbs(client)


@router.get("/wb/fbo", response_model=list[WbStockFbo])
def wb_fbo(client: Client = Depends(get_ch_client)):
    return fetch_wb_stocks_fbo(client)


@router.get("/wb/fbs", response_model=list[WbStockFbs])
def wb_fbs(client: Client = Depends(get_ch_client)):
    return fetch_wb_stocks_fbs(client)
