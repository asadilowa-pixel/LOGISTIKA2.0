import datetime
from dataclasses import dataclass


@dataclass
class OzonStockFbo:
    sku: int
    article_seller: str
    name_goods: str
    stocks: int
    on_way: int
    reserv: int
    sklad_name: str
    name_cabinet: str
    id_cabinet: int
    id_client: int
    update_at: datetime.datetime


@dataclass
class OzonStockFbs:
    sku: int
    article_seller: str
    stocks: int
    reserv: int
    warehouse_id: int
    sklad_name: str
    name_cabinet: str
    id_cabinet: int
    id_client: int
    update_at: datetime.datetime


@dataclass
class WbStockFbo:
    sklad: str
    article_seller: str
    article: int
    barcode: str
    stocks_current_day: int | None
    to_customer: int | None
    from_customer: int | None
    stocks_current_day_full: int | None
    category: str
    subject: str
    brand: str
    tech_size: str
    price: float | None
    discount: float | None
    name_cabinet: str
    id_client: int
    id_cabinet: int


@dataclass
class WbStockFbs:
    article: str
    article_seller: str
    stocks: int
    sklad: str
    barcode: str
    subject: str
    brand: str
    cabinet_name: str
    id_client: int
    id_cabinet: int
    photo: str
    ssilka: str
    sebes: float
    tag: str
    tag_obj: str


@dataclass
class WatchdogFreshness:
    run_id: str
    checked_at: datetime.datetime
    spreadsheet_id: str
    spreadsheet_name: str
    sheet_name: str
    filled_by: str
    date_column: str
    last_date: datetime.date | None
    lag_days: int | None
    allowed_days: int
    verdict: str
    detail: str


@dataclass
class WatchdogRun:
    run_id: str
    started_at: datetime.datetime
    finished_at: datetime.datetime
    refreshed: int
    ok: int
    waiting: int
    deferred: int
    problems: int
    fixed: int
    no_access: int
    mail_status: str
