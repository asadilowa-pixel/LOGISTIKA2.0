# Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single-page web dashboard (`GET /`) protected by HTTP Basic Auth, showing unified stocks, Ozon/WB logistics expenses, and Ozon/WB FBS order counts, all backed by two new JSON endpoints plus the existing `/stocks/unified`.

**Architecture:** A Starlette `BaseHTTPMiddleware` gates the whole FastAPI app behind HTTP Basic Auth (one shared login/password from `.env`). Two new repository functions query `ozon.expenses_agg`/`wildberies.logistics_costs` and `ozon.ozon_fbs_postings`/`wildberies.orders` for a date range, exposed as `GET /expenses/logistics` and `GET /orders/fbs-count`. A static HTML page with vanilla JS (`app/static/dashboard.html` + `.js` + `.css`) calls these plus the existing `/stocks/unified` via `fetch` and renders three sections.

**Tech Stack:** No new dependencies — `fastapi`/`starlette` already provide `BaseHTTPMiddleware`, `StaticFiles`, and `FileResponse`; `pydantic.BaseModel` (already a `fastapi` dependency) for the two new aggregate response models.

**Spec:** `docs/superpowers/specs/2026-09-09-dashboard-design.md`

## Global Constraints

- Auth is one ASGI middleware covering the entire app (HTML page, static assets, and every JSON endpoint) — not a per-route `Depends()`, because `Depends()` does not cover a `StaticFiles` mount.
- Password comparison uses `secrets.compare_digest`, never `==`.
- All ClickHouse queries use `{name:Type}` parameters — never string-interpolate a filter value into SQL.
- `date_from`/`date_to` are required query params on both new endpoints; `date_from > date_to` → `HTTP 400`.
- `wildberies.logistics_costs` has **no `id_client` column** (confirmed via `DESCRIBE TABLE` — only `date, sklad, barcode, sales_qt, return_qt, logistics_cost, reverse_logistics_cost`) — the WB logistics query must never filter on `id_client`, only on `date`.
- "No data" (`null`) for a block is decided by a real `count()` query against the same `WHERE` as the data query — never hardcoded — so it stays correct once the external pipeline starts writing WB logistics rows.
- No Jinja2, no SPA framework, no npm/node/build step — plain static HTML/CSS/JS served by FastAPI.
- No charts, no Excel export, no stocks-table pagination, no user roles — single shared login/password (YAGNI, per spec "Вне рамок").
- Automated tests never hit the live ClickHouse server — use `tests/fake_client.py`'s `FakeClient`/`FakeQueryResult`. Manual verification against the live server (`151.247.208.105:8123`) happens once at the end (Task 5), as has been done for every prior feature in this project.

---

## File Structure

```
app/
├── auth.py                          # NEW: BasicAuthMiddleware
├── config.py                        # MODIFY: + dashboard_user, dashboard_password
├── main.py                          # MODIFY: + auth middleware, + StaticFiles mount, + dashboard_router
├── models.py                        # MODIFY: + OzonLogisticsExpenses, WbLogisticsExpenses,
│                                     #   LogisticsExpenses, FbsOrderCount (all pydantic BaseModel)
├── repositories.py                  # MODIFY: + fetch_logistics_expenses(), fetch_fbs_order_count()
├── routers/
│   └── dashboard.py                 # NEW: GET /, GET /expenses/logistics, GET /orders/fbs-count
└── static/
    ├── dashboard.html               # NEW
    ├── dashboard.css                # NEW
    └── dashboard.js                 # NEW
.env.example                         # MODIFY: + DASHBOARD_USER, DASHBOARD_PASSWORD
tests/
├── fake_client.py                   # MODIFY: FakeClient.query supports list-of-results mode
├── test_auth.py                     # NEW: middleware unit tests + GET / auth coverage
├── test_expenses_and_orders.py      # NEW: repository-level tests for the two new fetch_*
├── test_dashboard_endpoints.py      # NEW: router-level tests for the two new JSON endpoints
├── test_routers.py                  # MODIFY: TestClient(app) → TestClient(app, auth=...)
└── test_filters.py                  # MODIFY: TestClient(app) → TestClient(app, auth=...)
```

---

### Task 1: Dashboard auth — config, middleware, wire into main.py

**Files:**
- Modify: `app/config.py`
- Create: `app/auth.py`
- Modify: `app/main.py`
- Modify: `.env.example`
- Modify: `tests/test_routers.py` (fix tests broken by the new global middleware)
- Modify: `tests/test_filters.py` (fix tests broken by the new global middleware)
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `app.config.settings` (existing)
- Produces: `app.auth.BasicAuthMiddleware` (Starlette `BaseHTTPMiddleware` subclass); `settings.dashboard_user: str`, `settings.dashboard_password: str` (both default to `"admin"` so the app runs out of the box; real deployments should override in `.env`)

- [ ] **Step 1: Add dashboard auth settings**

Edit `app/config.py` — add two fields to `Settings`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "default"

    dashboard_user: str = "admin"
    dashboard_password: str = "admin"


settings = Settings()
```

- [ ] **Step 2: Add the new vars to `.env.example`**

Append to `.env.example`:

```
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=change-me
```

- [ ] **Step 3: Write the failing middleware tests**

Create `tests/test_auth.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.config as config_module


def _make_app():
    from app.auth import BasicAuthMiddleware

    test_app = FastAPI()
    test_app.add_middleware(BasicAuthMiddleware)

    @test_app.get("/ping")
    def ping():
        return {"ok": True}

    return test_app


def test_no_credentials_returns_401(monkeypatch):
    monkeypatch.setattr(config_module.settings, "dashboard_user", "admin")
    monkeypatch.setattr(config_module.settings, "dashboard_password", "secret")
    client = TestClient(_make_app())

    resp = client.get("/ping")

    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"].startswith("Basic")


def test_wrong_password_returns_401(monkeypatch):
    monkeypatch.setattr(config_module.settings, "dashboard_user", "admin")
    monkeypatch.setattr(config_module.settings, "dashboard_password", "secret")
    client = TestClient(_make_app())

    resp = client.get("/ping", auth=("admin", "wrong"))

    assert resp.status_code == 401


def test_wrong_username_returns_401(monkeypatch):
    monkeypatch.setattr(config_module.settings, "dashboard_user", "admin")
    monkeypatch.setattr(config_module.settings, "dashboard_password", "secret")
    client = TestClient(_make_app())

    resp = client.get("/ping", auth=("someone-else", "secret"))

    assert resp.status_code == 401


def test_correct_credentials_returns_200(monkeypatch):
    monkeypatch.setattr(config_module.settings, "dashboard_user", "admin")
    monkeypatch.setattr(config_module.settings, "dashboard_password", "secret")
    client = TestClient(_make_app())

    resp = client.get("/ping", auth=("admin", "secret"))

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_malformed_authorization_header_returns_401(monkeypatch):
    monkeypatch.setattr(config_module.settings, "dashboard_user", "admin")
    monkeypatch.setattr(config_module.settings, "dashboard_password", "secret")
    client = TestClient(_make_app())

    resp = client.get("/ping", headers={"Authorization": "Bearer not-basic-auth"})

    assert resp.status_code == 401
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth'`

- [ ] **Step 5: Write `app/auth.py`**

```python
import base64
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not _has_valid_credentials(request.headers.get("Authorization")):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Сервис логиста"'},
            )
        return await call_next(request)


def _has_valid_credentials(authorization_header: str | None) -> bool:
    if not authorization_header or not authorization_header.startswith("Basic "):
        return False
    encoded = authorization_header[len("Basic "):]
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    username, _, password = decoded.partition(":")
    return secrets.compare_digest(username, settings.dashboard_user) and secrets.compare_digest(
        password, settings.dashboard_password
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Wire the middleware into `main.py`**

Edit `app/main.py` — full new content:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth import BasicAuthMiddleware
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
app.add_middleware(BasicAuthMiddleware)
app.include_router(stocks_router)
app.include_router(watchdog_router)
app.include_router(mysklad_router)
```

- [ ] **Step 8: Run the full suite — existing router tests now fail on 401**

Run: `pytest -v`
Expected: FAIL — every test in `tests/test_routers.py` and `tests/test_filters.py` that
instantiates `TestClient(app)` now gets `401` instead of the expected `200`/`400`, because the
middleware from Step 7 now guards every route. This is expected at this point in the task.

- [ ] **Step 9: Fix `tests/test_routers.py` to authenticate**

Edit `tests/test_routers.py` — two changes: add the settings import, and pass `auth=` when
building the `TestClient`.

Change the import block (top of file) from:

```python
import datetime

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_ch_client
from app.main import app
from tests.fake_client import FakeClient, FakeQueryResult
```

to:

```python
import datetime

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import get_ch_client
from app.main import app
from tests.fake_client import FakeClient, FakeQueryResult
```

Change the `client_with` fixture's `_make` function from:

```python
    def _make(result: FakeQueryResult) -> TestClient:
        fake = FakeClient(result)
        app.dependency_overrides[get_ch_client] = lambda: fake
        return TestClient(app)
```

to:

```python
    def _make(result: FakeQueryResult) -> TestClient:
        fake = FakeClient(result)
        app.dependency_overrides[get_ch_client] = lambda: fake
        return TestClient(app, auth=(settings.dashboard_user, settings.dashboard_password))
```

- [ ] **Step 10: Fix `tests/test_filters.py` to authenticate**

Edit `tests/test_filters.py` — add the settings import and pass `auth=` at both `TestClient(app)`
call sites.

Change the import block from:

```python
from fastapi.testclient import TestClient

from app.dependencies import get_ch_client
from app.main import app
from app.repositories import (
    fetch_mysklad_supplies_marketplaces,
    fetch_ozon_stocks_fbo,
    fetch_unified_stocks,
)
from tests.fake_client import FakeClient, FakeQueryResult
```

to:

```python
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import get_ch_client
from app.main import app
from app.repositories import (
    fetch_mysklad_supplies_marketplaces,
    fetch_ozon_stocks_fbo,
    fetch_unified_stocks,
)
from tests.fake_client import FakeClient, FakeQueryResult
```

In `test_unified_endpoint_rejects_invalid_marketplace`, change:

```python
    app.dependency_overrides[get_ch_client] = lambda: FakeClient(FakeQueryResult([], []))
    client = TestClient(app)
```

to:

```python
    app.dependency_overrides[get_ch_client] = lambda: FakeClient(FakeQueryResult([], []))
    client = TestClient(app, auth=(settings.dashboard_user, settings.dashboard_password))
```

In `test_unified_endpoint_accepts_valid_marketplace`, change:

```python
    app.dependency_overrides[get_ch_client] = lambda: fake
    client = TestClient(app)
```

to:

```python
    app.dependency_overrides[get_ch_client] = lambda: fake
    client = TestClient(app, auth=(settings.dashboard_user, settings.dashboard_password))
```

- [ ] **Step 11: Run the full suite to verify everything passes again**

Run: `pytest -v`
Expected: PASS (all tests — 24 pre-existing + 5 new from `test_auth.py` = 29)

- [ ] **Step 12: Commit**

```bash
git add app/config.py app/auth.py app/main.py .env.example tests/test_auth.py tests/test_routers.py tests/test_filters.py
git commit -m "feat: HTTP Basic Auth middleware covering the whole app"
```

---

### Task 2: Logistics expenses and FBS order count — models and repository functions

**Files:**
- Modify: `app/models.py`
- Modify: `app/repositories.py`
- Modify: `tests/fake_client.py`
- Test: `tests/test_expenses_and_orders.py`

**Interfaces:**
- Consumes: `app.repositories._where_clause` is NOT reused here (it only supports `=`, these
  queries need `BETWEEN`) — new queries are built inline in the two new functions.
- Produces: `app.models.OzonLogisticsExpenses`, `app.models.WbLogisticsExpenses`,
  `app.models.LogisticsExpenses`, `app.models.FbsOrderCount` (all `pydantic.BaseModel`);
  `app.repositories.fetch_logistics_expenses(client, date_from: datetime.date, date_to: datetime.date, id_client: int | None = None) -> LogisticsExpenses`;
  `app.repositories.fetch_fbs_order_count(client, date_from: datetime.date, date_to: datetime.date, id_client: int | None = None) -> FbsOrderCount`

- [ ] **Step 1: Extend `FakeClient` to support an ordered sequence of results**

`fetch_logistics_expenses`/`fetch_fbs_order_count` issue 2-4 sequential `client.query()` calls
per invocation (count, then conditionally sum) against different tables that can share a
substring match, so the existing single-result/dict-by-table-substring modes can't distinguish
them. Add a third mode: pass a `list` of `FakeQueryResult` and each call pops the next one.

Edit `tests/fake_client.py` — change the `query` method from:

```python
    def query(self, sql: str, parameters: dict | None = None):
        self.queries.append(sql)
        self.query_params.append(parameters)
        if isinstance(self.result, dict):
            for key, value in self.result.items():
                if key in sql:
                    return value
            raise KeyError(f"no fake result configured for query: {sql}")
        return self.result
```

to:

```python
    def query(self, sql: str, parameters: dict | None = None):
        self.queries.append(sql)
        self.query_params.append(parameters)
        if isinstance(self.result, dict):
            for key, value in self.result.items():
                if key in sql:
                    return value
            raise KeyError(f"no fake result configured for query: {sql}")
        if isinstance(self.result, list):
            return self.result.pop(0)
        return self.result
```

Also update the class docstring to mention the new mode — change:

```python
class FakeClient:
    """Stands in for clickhouse_connect's Client in tests. Every call is
    recorded so tests can assert on the table/limit that was actually
    queried. `result` is either a single FakeQueryResult returned for every
    call, or a dict of {table-name-substring: FakeQueryResult} for callers
    (like fetch_unified_stocks) that query more than one table."""
```

to:

```python
class FakeClient:
    """Stands in for clickhouse_connect's Client in tests. Every call is
    recorded so tests can assert on the table/limit that was actually
    queried. `result` is a single FakeQueryResult returned for every call, a
    dict of {table-name-substring: FakeQueryResult} for callers (like
    fetch_unified_stocks) that query more than one table, or a list of
    FakeQueryResult consumed in call order for callers (like
    fetch_logistics_expenses) that issue several sequential queries against
    the same table (e.g. a count() then a sum())."""
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_expenses_and_orders.py`:

```python
import datetime

from app.repositories import fetch_fbs_order_count, fetch_logistics_expenses
from tests.fake_client import FakeClient, FakeQueryResult

DATE_FROM = datetime.date(2026, 8, 1)
DATE_TO = datetime.date(2026, 8, 31)


def test_fetch_logistics_expenses_ozon_has_data_wb_empty():
    client = FakeClient([
        FakeQueryResult([], [(5,)]),  # ozon count > 0
        FakeQueryResult([], [(100.0, 10.0, 20.0, 1.0)]),  # ozon sums
        FakeQueryResult([], [(0,)]),  # wb count == 0
    ])

    result = fetch_logistics_expenses(client, DATE_FROM, DATE_TO)

    assert result.date_from == DATE_FROM
    assert result.date_to == DATE_TO
    assert result.ozon.logistics_cost == 100.0
    assert result.ozon.returned_logistics_cost == 10.0
    assert result.ozon.last_mile_cost == 20.0
    assert result.ozon.cancel_last_mile_cost == 1.0
    assert result.ozon.total == 131.0
    assert result.wb is None


def test_fetch_logistics_expenses_ozon_empty_period():
    client = FakeClient([
        FakeQueryResult([], [(0,)]),  # ozon count == 0
        FakeQueryResult([], [(0,)]),  # wb count == 0
    ])

    result = fetch_logistics_expenses(client, DATE_FROM, DATE_TO)

    assert result.ozon is None
    assert result.wb is None


def test_fetch_logistics_expenses_wb_has_data():
    client = FakeClient([
        FakeQueryResult([], [(0,)]),  # ozon count == 0
        FakeQueryResult([], [(3,)]),  # wb count > 0
        FakeQueryResult([], [(50.0, 5.0)]),  # wb sums
    ])

    result = fetch_logistics_expenses(client, DATE_FROM, DATE_TO)

    assert result.ozon is None
    assert result.wb.logistics_cost == 50.0
    assert result.wb.reverse_logistics_cost == 5.0
    assert result.wb.total == 55.0


def test_fetch_logistics_expenses_id_client_filters_ozon_only():
    client = FakeClient([
        FakeQueryResult([], [(0,)]),
        FakeQueryResult([], [(0,)]),
    ])

    fetch_logistics_expenses(client, DATE_FROM, DATE_TO, id_client=1)

    assert "id_client = {id_client:UInt8}" in client.queries[0]
    assert client.query_params[0]["id_client"] == 1
    # wildberies.logistics_costs has no id_client column
    assert "id_client" not in client.queries[1]
    assert "id_client" not in client.query_params[1]


def test_fetch_logistics_expenses_queries_correct_tables():
    client = FakeClient([
        FakeQueryResult([], [(0,)]),
        FakeQueryResult([], [(0,)]),
    ])

    fetch_logistics_expenses(client, DATE_FROM, DATE_TO)

    assert "ozon.expenses_agg" in client.queries[0]
    assert "wildberies.logistics_costs" in client.queries[1]


def test_fetch_fbs_order_count_maps_both_marketplaces():
    client = FakeClient([
        FakeQueryResult([], [(12,)]),  # ozon count
        FakeQueryResult([], [(7,)]),   # wb count
    ])

    result = fetch_fbs_order_count(client, DATE_FROM, DATE_TO)

    assert result.date_from == DATE_FROM
    assert result.date_to == DATE_TO
    assert result.ozon == 12
    assert result.wb == 7
    assert "ozon.ozon_fbs_postings" in client.queries[0]
    assert "wildberies.orders" in client.queries[1]
    assert "fbs = true" in client.queries[1]


def test_fetch_fbs_order_count_id_client_filters_both():
    client = FakeClient([
        FakeQueryResult([], [(0,)]),
        FakeQueryResult([], [(0,)]),
    ])

    fetch_fbs_order_count(client, DATE_FROM, DATE_TO, id_client=1)

    assert client.query_params[0]["id_client"] == 1
    assert client.query_params[1]["id_client"] == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_expenses_and_orders.py -v`
Expected: FAIL — `ImportError: cannot import name 'fetch_logistics_expenses'`

- [ ] **Step 4: Add the four new models**

Edit `app/models.py` — add the `BaseModel` import at the top (change line 1-2 from):

```python
import datetime
from dataclasses import dataclass
```

to:

```python
import datetime
from dataclasses import dataclass

from pydantic import BaseModel
```

Then append at the end of the file (after `WatchdogRun`):

```python


class OzonLogisticsExpenses(BaseModel):
    logistics_cost: float
    returned_logistics_cost: float
    last_mile_cost: float
    cancel_last_mile_cost: float
    total: float


class WbLogisticsExpenses(BaseModel):
    logistics_cost: float
    reverse_logistics_cost: float
    total: float


class LogisticsExpenses(BaseModel):
    date_from: datetime.date
    date_to: datetime.date
    ozon: OzonLogisticsExpenses | None
    wb: WbLogisticsExpenses | None


class FbsOrderCount(BaseModel):
    date_from: datetime.date
    date_to: datetime.date
    ozon: int
    wb: int
```

- [ ] **Step 5: Add the two repository functions**

Edit `app/repositories.py` — add `datetime` to the imports (change line 1 from):

```python
from clickhouse_connect.driver.client import Client
```

to:

```python
import datetime

from clickhouse_connect.driver.client import Client
```

Add `LogisticsExpenses`, `FbsOrderCount`, `OzonLogisticsExpenses`, `WbLogisticsExpenses` to the
`app.models` import block (change it from):

```python
from app.models import (
    MyskladOrderSupply,
    MyskladSupplyMarketplace,
    OzonStockFbo,
    OzonStockFbs,
    UnifiedStock,
    WatchdogFreshness,
    WatchdogRun,
    WbStockFbo,
    WbStockFbs,
)
```

to:

```python
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
```

Append at the end of the file:

```python


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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_expenses_and_orders.py -v`
Expected: PASS (7 tests)

- [ ] **Step 7: Run the full suite**

Run: `pytest -v`
Expected: PASS (all 36 tests: 29 from Task 1 + 7 new)

- [ ] **Step 8: Commit**

```bash
git add app/models.py app/repositories.py tests/fake_client.py tests/test_expenses_and_orders.py
git commit -m "feat: logistics expenses and FBS order count repository functions"
```

---

### Task 3: Dashboard JSON endpoints

**Files:**
- Create: `app/routers/dashboard.py`
- Modify: `app/main.py`
- Test: `tests/test_dashboard_endpoints.py`

**Interfaces:**
- Consumes: `app.repositories.fetch_logistics_expenses`, `app.repositories.fetch_fbs_order_count` (Task 2); `app.dependencies.get_ch_client` (existing)
- Produces: `app.routers.dashboard.router` (`APIRouter`) with `GET /expenses/logistics` and `GET /orders/fbs-count`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dashboard_endpoints.py`:

```python
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import get_ch_client
from app.main import app
from tests.fake_client import FakeClient, FakeQueryResult


def _authed_client(fake: FakeClient) -> TestClient:
    app.dependency_overrides[get_ch_client] = lambda: fake
    return TestClient(app, auth=(settings.dashboard_user, settings.dashboard_password))


def test_expenses_logistics_endpoint_returns_ozon_and_null_wb():
    fake = FakeClient([
        FakeQueryResult([], [(5,)]),
        FakeQueryResult([], [(100.0, 10.0, 20.0, 1.0)]),
        FakeQueryResult([], [(0,)]),
    ])
    client = _authed_client(fake)

    resp = client.get(
        "/expenses/logistics", params={"date_from": "2026-08-01", "date_to": "2026-08-31"}
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["ozon"]["total"] == 131.0
    assert body["wb"] is None


def test_expenses_logistics_rejects_inverted_date_range():
    client = _authed_client(FakeClient([]))

    resp = client.get(
        "/expenses/logistics", params={"date_from": "2026-08-31", "date_to": "2026-08-01"}
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_expenses_logistics_requires_date_params():
    client = _authed_client(FakeClient([]))

    resp = client.get("/expenses/logistics")

    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_orders_fbs_count_endpoint():
    fake = FakeClient([
        FakeQueryResult([], [(12,)]),
        FakeQueryResult([], [(7,)]),
    ])
    client = _authed_client(fake)

    resp = client.get(
        "/orders/fbs-count", params={"date_from": "2026-08-01", "date_to": "2026-08-31"}
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["ozon"] == 12
    assert body["wb"] == 7


def test_orders_fbs_count_rejects_inverted_date_range():
    client = _authed_client(FakeClient([]))

    resp = client.get(
        "/orders/fbs-count", params={"date_from": "2026-08-31", "date_to": "2026-08-01"}
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_expenses_logistics_requires_auth():
    fake = FakeClient([])
    app.dependency_overrides[get_ch_client] = lambda: fake
    client = TestClient(app)

    resp = client.get(
        "/expenses/logistics", params={"date_from": "2026-08-01", "date_to": "2026-08-31"}
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard_endpoints.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.dashboard'`

- [ ] **Step 3: Write `app/routers/dashboard.py`**

```python
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
```

- [ ] **Step 4: Wire the router into `main.py`**

Edit `app/main.py` — add the import (change the router import block from):

```python
from app.auth import BasicAuthMiddleware
from app.db import get_client
from app.routers.mysklad import router as mysklad_router
from app.routers.stocks import router as stocks_router
from app.routers.watchdog import router as watchdog_router
```

to:

```python
from app.auth import BasicAuthMiddleware
from app.db import get_client
from app.routers.dashboard import router as dashboard_router
from app.routers.mysklad import router as mysklad_router
from app.routers.stocks import router as stocks_router
from app.routers.watchdog import router as watchdog_router
```

and add `app.include_router(dashboard_router)` after the existing `include_router` calls (change):

```python
app.include_router(stocks_router)
app.include_router(watchdog_router)
app.include_router(mysklad_router)
```

to:

```python
app.include_router(stocks_router)
app.include_router(watchdog_router)
app.include_router(mysklad_router)
app.include_router(dashboard_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_dashboard_endpoints.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Run the full suite**

Run: `pytest -v`
Expected: PASS (all 42 tests: 36 from Tasks 1-2 + 6 new)

- [ ] **Step 7: Commit**

```bash
git add app/routers/dashboard.py app/main.py tests/test_dashboard_endpoints.py
git commit -m "feat: dashboard JSON endpoints for logistics expenses and FBS order counts"
```

---

### Task 4: Dashboard page (static HTML/CSS/JS)

**Files:**
- Create: `app/static/dashboard.html`
- Create: `app/static/dashboard.css`
- Create: `app/static/dashboard.js`
- Modify: `app/routers/dashboard.py`
- Modify: `app/main.py`
- Modify: `tests/test_auth.py`

**Interfaces:**
- Consumes: `GET /stocks/unified` (existing), `GET /expenses/logistics`, `GET /orders/fbs-count` (Task 3) — all called client-side via `fetch`
- Produces: `GET /` returns `app/static/dashboard.html`; `/static/*` serves `dashboard.css`/`dashboard.js`

- [ ] **Step 1: Write the failing auth-coverage tests for the page**

Append to `tests/test_auth.py`:

```python


def test_dashboard_page_requires_auth():
    from app.main import app as real_app

    client = TestClient(real_app)

    resp = client.get("/")

    assert resp.status_code == 401


def test_dashboard_page_served_with_auth():
    from app.config import settings as real_settings
    from app.main import app as real_app

    client = TestClient(
        real_app, auth=(real_settings.dashboard_user, real_settings.dashboard_password)
    )

    resp = client.get("/")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL — `test_dashboard_page_requires_auth` gets `404` (route doesn't exist yet, not
`401`); `test_dashboard_page_served_with_auth` also fails with `404`.

- [ ] **Step 3: Write `app/static/dashboard.html`**

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Сервис логиста 2.0 — Дашборд</title>
    <link rel="stylesheet" href="/static/dashboard.css">
</head>
<body>
    <h1>Сервис логиста 2.0</h1>

    <section id="filters">
        <label>Период: с <input type="date" id="date-from"></label>
        <label>по <input type="date" id="date-to"></label>
        <label>ID клиента: <input type="number" id="id-client" placeholder="все"></label>
    </section>

    <section id="stocks-section">
        <h2>Остатки</h2>
        <label>Маркетплейс:
            <select id="stocks-marketplace">
                <option value="">Все</option>
                <option value="ozon">Ozon</option>
                <option value="wb">WB</option>
            </select>
        </label>
        <table>
            <thead>
                <tr>
                    <th>Маркетплейс</th>
                    <th>Тип</th>
                    <th>Артикул</th>
                    <th>Склад</th>
                    <th>Кол-во</th>
                    <th>Кабинет</th>
                </tr>
            </thead>
            <tbody id="stocks-body"></tbody>
        </table>
    </section>

    <section id="expenses-section">
        <h2>Расходы на логистику</h2>
        <div class="cards">
            <div class="card">
                <h3>Ozon</h3>
                <div id="expenses-ozon">—</div>
            </div>
            <div class="card">
                <h3>WB</h3>
                <div id="expenses-wb">—</div>
            </div>
        </div>
    </section>

    <section id="fbs-section">
        <h2>Заказы ФБС</h2>
        <div class="cards">
            <div class="card">
                <h3>Ozon</h3>
                <div id="fbs-ozon">—</div>
            </div>
            <div class="card">
                <h3>WB</h3>
                <div id="fbs-wb">—</div>
            </div>
        </div>
    </section>

    <script src="/static/dashboard.js"></script>
</body>
</html>
```

- [ ] **Step 4: Write `app/static/dashboard.css`**

```css
body {
    font-family: system-ui, sans-serif;
    margin: 2rem;
    color: #1a1a1a;
}

h1 {
    margin-bottom: 1.5rem;
}

section {
    margin-bottom: 2rem;
}

#filters label {
    margin-right: 1.5rem;
}

table {
    border-collapse: collapse;
    width: 100%;
}

th, td {
    border: 1px solid #ccc;
    padding: 0.4rem 0.6rem;
    text-align: left;
}

th {
    background: #f0f0f0;
}

.cards {
    display: flex;
    gap: 1rem;
}

.card {
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 1rem;
    min-width: 220px;
}

.card h3 {
    margin-top: 0;
}
```

- [ ] **Step 5: Write `app/static/dashboard.js`**

```javascript
function toIsoDate(date) {
    return date.toISOString().slice(0, 10);
}

function setDefaultDateRange() {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - 30);
    document.getElementById("date-from").value = toIsoDate(from);
    document.getElementById("date-to").value = toIsoDate(to);
}

function buildQuery(params) {
    const usp = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (value !== null && value !== undefined && value !== "") {
            usp.set(key, value);
        }
    }
    return usp.toString();
}

function currentPeriodAndClient() {
    return {
        date_from: document.getElementById("date-from").value,
        date_to: document.getElementById("date-to").value,
        id_client: document.getElementById("id-client").value,
    };
}

async function fetchStocks() {
    const marketplace = document.getElementById("stocks-marketplace").value;
    const idClient = document.getElementById("id-client").value;
    const query = buildQuery({ marketplace, id_client: idClient });
    const resp = await fetch(`/stocks/unified?${query}`);
    const rows = await resp.json();

    const body = document.getElementById("stocks-body");
    body.innerHTML = "";
    for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${row.marketplace}</td>
            <td>${row.fulfillment}</td>
            <td>${row.article_seller}</td>
            <td>${row.warehouse}</td>
            <td>${row.quantity}</td>
            <td>${row.cabinet}</td>
        `;
        body.appendChild(tr);
    }
}

const EXPENSE_FIELD_LABELS = {
    logistics_cost: "Логистика",
    returned_logistics_cost: "Возвраты логистики",
    last_mile_cost: "Последняя миля",
    cancel_last_mile_cost: "Отмена последней мили",
    reverse_logistics_cost: "Обратная логистика",
};

function renderExpensesCard(elementId, data) {
    const el = document.getElementById(elementId);
    if (data === null || data === undefined) {
        el.textContent = "нет данных";
        return;
    }
    let html = "";
    for (const [key, value] of Object.entries(data)) {
        if (key === "total") continue;
        const label = EXPENSE_FIELD_LABELS[key] || key;
        html += `<div>${label}: ${value.toFixed(2)}</div>`;
    }
    html += `<div><strong>Итого: ${data.total.toFixed(2)}</strong></div>`;
    el.innerHTML = html;
}

async function fetchExpenses() {
    const query = buildQuery(currentPeriodAndClient());
    const resp = await fetch(`/expenses/logistics?${query}`);
    const data = await resp.json();
    renderExpensesCard("expenses-ozon", data.ozon);
    renderExpensesCard("expenses-wb", data.wb);
}

async function fetchFbsCounts() {
    const query = buildQuery(currentPeriodAndClient());
    const resp = await fetch(`/orders/fbs-count?${query}`);
    const data = await resp.json();
    document.getElementById("fbs-ozon").textContent = data.ozon;
    document.getElementById("fbs-wb").textContent = data.wb;
}

function refreshPeriodBlocks() {
    fetchExpenses();
    fetchFbsCounts();
}

function refreshAll() {
    fetchStocks();
    refreshPeriodBlocks();
}

function init() {
    setDefaultDateRange();
    document.getElementById("date-from").addEventListener("change", refreshPeriodBlocks);
    document.getElementById("date-to").addEventListener("change", refreshPeriodBlocks);
    document.getElementById("id-client").addEventListener("change", refreshAll);
    document.getElementById("stocks-marketplace").addEventListener("change", fetchStocks);
    refreshAll();
}

document.addEventListener("DOMContentLoaded", init);
```

- [ ] **Step 6: Add the `GET /` route**

Edit `app/routers/dashboard.py` — add imports and the route. Change the top of the file from:

```python
import datetime

from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_ch_client
from app.models import FbsOrderCount, LogisticsExpenses
from app.repositories import fetch_fbs_order_count, fetch_logistics_expenses

router = APIRouter(tags=["dashboard"])
```

to:

```python
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
```

- [ ] **Step 7: Mount `/static` in `main.py`**

Edit `app/main.py` — add the `StaticFiles` import and mount. Change from:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth import BasicAuthMiddleware
from app.db import get_client
from app.routers.dashboard import router as dashboard_router
from app.routers.mysklad import router as mysklad_router
from app.routers.stocks import router as stocks_router
from app.routers.watchdog import router as watchdog_router


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
```

to:

```python
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
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS (7 tests)

- [ ] **Step 9: Run the full suite**

Run: `pytest -v`
Expected: PASS (all 44 tests: 42 from Tasks 1-3 + 2 new)

- [ ] **Step 10: Commit**

```bash
git add app/static app/routers/dashboard.py app/main.py tests/test_auth.py
git commit -m "feat: dashboard page (static HTML/CSS/JS) at GET /"
```

---

### Task 5: Manual end-to-end verification against the live server

**Files:**
- Modify: none (verification only)

**Interfaces:**
- Consumes: everything from Tasks 1-4

- [ ] **Step 1: Run the full automated test suite one more time**

Run: `pytest -v`
Expected: PASS (44 tests, 0 failures)

- [ ] **Step 2: Start the app against the real ClickHouse server**

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Expected: starts cleanly, no traceback (connects to `151.247.208.105:8123` on startup, as it has
for every prior feature).

- [ ] **Step 3: Verify auth is enforced**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
```

Expected: `401` (no credentials sent).

- [ ] **Step 4: Verify the page loads with credentials**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -u admin:admin http://127.0.0.1:8000/
curl -s -o /dev/null -w "%{http_code}\n" -u admin:admin http://127.0.0.1:8000/static/dashboard.js
curl -s -o /dev/null -w "%{http_code}\n" -u admin:admin http://127.0.0.1:8000/static/dashboard.css
```

Expected: `200` for all three (using the default `admin`/`admin` unless `.env` overrides them).

- [ ] **Step 5: Verify the two new endpoints against live data**

```bash
curl -s -u admin:admin "http://127.0.0.1:8000/expenses/logistics?date_from=2026-08-01&date_to=2026-09-09"
curl -s -u admin:admin "http://127.0.0.1:8000/orders/fbs-count?date_from=2026-08-01&date_to=2026-09-09"
```

Expected: `expenses/logistics` returns a populated `ozon` object with a non-zero `total` and
`wb: null` (table still empty on the live server per Task 2's Global Constraints); `orders/fbs-count`
returns non-zero integers for both `ozon` and `wb`.

- [ ] **Step 6: Open the dashboard in a browser**

Navigate to `http://127.0.0.1:8000/`, enter the `admin`/`admin` credentials at the browser's
Basic Auth prompt, and confirm all three sections render real data: the stocks table has rows,
the Ozon expenses card shows non-zero numbers (WB shows "нет данных"), and both FBS order-count
cards show non-zero numbers. Change the date range and confirm the expenses/FBS cards update;
change the marketplace filter and confirm the stocks table updates.

- [ ] **Step 7: Stop the server**

```bash
# Ctrl+C, or on Windows: taskkill on the uvicorn PID
```

- [ ] **Step 8: Remind the user to set a real password**

No code change — just a note for whoever deploys this: the default `admin`/`admin` credentials
(`app/config.py` Step 1 of Task 1) are fine for this manual check, but `DASHBOARD_USER` and
`DASHBOARD_PASSWORD` should be set to real values in the project's `.env` before the team starts
using this on the shared network.

No commit for this task — it's verification only, nothing new to add to git.

---

## Self-Review Notes

- **Spec coverage:** Auth (Task 1), `/expenses/logistics` with real count-based `wb: null`
  (Task 2 repository + Task 3 route), `/orders/fbs-count` (Task 2 + Task 3), the three-section
  `GET /` page with period/marketplace/id_client filters (Task 4), manual live verification
  (Task 5) — every section of `2026-09-09-dashboard-design.md` maps to a task.
- **Deviation from spec, called out explicitly:** the spec's SQL sketch for `/expenses/logistics`
  didn't show the WB query; live `DESCRIBE TABLE wildberies.logistics_costs` (re-verified while
  writing this plan) shows that table has **no `id_client` column**, so Task 2's WB query
  correctly omits that filter — this is now a Global Constraint, not an oversight.
  `expenses_by_order`/`orders_expens` (also possible logistics-expense sources) were considered
  and rejected: `expenses_by_order` lacks a date column to range-filter on, and `orders_expens`
  has 0 rows.
- **Type/signature consistency:** `fetch_logistics_expenses(client, date_from, date_to, id_client=None) -> LogisticsExpenses` and `fetch_fbs_order_count(client, date_from, date_to, id_client=None) -> FbsOrderCount` are identical across Task 2 (definition) and Task 3 (route usage). `FakeClient`'s new list-mode (Task 2 Step 1) is used consistently in Task 2's and Task 3's tests.
- **Known ripple effect, handled in-task:** Task 1 Steps 8-11 explicitly walk through the fact
  that adding the global auth middleware breaks every pre-existing `TestClient(app)` call in
  `tests/test_routers.py` and `tests/test_filters.py`, and fixes both files in the same task —
  no task ends with a known-broken test suite.
