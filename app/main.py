from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import get_client
from app.routers.mysklad import router as mysklad_router
from app.routers.stocks import router as stocks_router
from app.routers.watchdog import router as watchdog_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ch_client = get_client()
    yield
    app.state.ch_client.close()


app = FastAPI(title="Сервис логиста 2.0", lifespan=lifespan)
app.include_router(stocks_router)
app.include_router(watchdog_router)
app.include_router(mysklad_router)
