from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth import BasicAuthMiddleware
from app.db import get_client
from app.routers.dashboard import router as dashboard_router
from app.routers.mysklad import router as mysklad_router
from app.routers.stocks import router as stocks_router
from app.routers.watchdog import router as watchdog_router

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ch_client = get_client()
    yield
    app.state.ch_client.close()


app = FastAPI(title="Сервис логиста 2.0", lifespan=lifespan)
app.add_middleware(BasicAuthMiddleware)
app.include_router(stocks_router)
app.include_router(watchdog_router)
app.include_router(mysklad_router)
app.include_router(dashboard_router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
