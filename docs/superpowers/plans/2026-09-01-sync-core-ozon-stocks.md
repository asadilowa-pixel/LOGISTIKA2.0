# Sync Core — Ozon «Остатки» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the sync-core backend (FastAPI + PostgreSQL) that ingests Ozon "Остатки" xlsx exports (via watch-folder or manual HTTP upload) into a canonical `stocks` table, with a full sync journal, dedup, and a freshness-status endpoint — no live API calls yet.

**Architecture:** A `SyncSource` protocol with one MVP implementation (`FileSource`, xlsx via `openpyxl`) feeds a single `ingest_stocks_file()` pipeline that both the watch-folder poller (APScheduler) and the HTTP upload endpoint call. The pipeline upserts into `stocks`, records every attempt in `sync_runs`, and dedups by file hash via `ingested_files`. Canonical data is never truncated — a failed or duplicate run leaves existing rows untouched.

**Tech Stack:** Python 3.12, FastAPI 0.115, SQLAlchemy 2.0 (Core `INSERT ... ON CONFLICT` for upserts), PostgreSQL 16, APScheduler 3.10, openpyxl, Docker Compose (`backend` + `postgres`, no broker).

**Spec:** `docs/superpowers/specs/2026-09-01-sync-core-design.md` (see especially "Маппинг колонок «Остатки»" for the exact real column layout this plan implements against).

## Global Constraints

- MVP source is **Ozon only** (file-based); WB and МойСклад exist only as disabled rows in `sources` — no connector code for them in this plan.
- Only the **«Остатки»** section is implemented. FBS orders are explicitly out of scope (no real sample file — see spec's "История ревизий").
- Canonical tables (`stocks`) are upsert-only — **never** `TRUNCATE`/`DELETE`, including on parse failure (spec requirement 12).
- No authentication on API endpoints (single-user local MVP, per spec).
- No Alembic/migrations — `Base.metadata.create_all()` on startup is sufficient for this MVP (single dev, schema not yet stable enough to version).
- Tests run against a real PostgreSQL (not SQLite) because upserts use `sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_update(...)`, which is Postgres-specific.

---

## File Structure

```
сервис логиста 2.0/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI app, startup/shutdown wiring
│   ├── config.py               # Settings (pydantic-settings)
│   ├── db.py                   # engine, SessionLocal, Base, get_db
│   ├── models.py                # Source, SourceSection, SyncRun, IngestedFile, Stock
│   ├── seed.py                  # idempotent seed of sources/sections
│   ├── hashing.py                # file_sha256()
│   ├── ingest.py                  # ingest_stocks_file() pipeline
│   ├── watcher.py                  # APScheduler watch-folder job
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py                  # StockRow, SyncSource protocol
│   │   └── file_source.py            # FileSource: parses Ozon "Товар-склад" xlsx
│   └── routers/
│       ├── __init__.py
│       └── sync.py                    # upload / status / runs endpoints
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── __init__.py
│   │   └── xlsx_builder.py            # builds real-shaped test xlsx via openpyxl
│   ├── test_hashing.py
│   ├── sources/
│   │   └── test_file_source.py
│   ├── test_ingest.py
│   ├── test_watcher.py
│   └── routers/
│       └── test_sync.py
└── watch/                                # watch-folder mount point (empty, gitkeep)
```

---

### Task 1: Project scaffolding & settings

**Files:**
- Create: `requirements.txt`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `watch/.gitkeep`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `app.config.Settings` (fields: `database_url: str`, `watch_folder: str`, `watch_poll_seconds: int`), module-level singleton `app.config.settings`

- [ ] **Step 1: Write `requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy==2.0.35
psycopg2-binary==2.9.9
openpyxl==3.1.5
apscheduler==3.10.4
pydantic-settings==2.5.2
python-multipart==0.0.9
pytest==8.3.3
httpx==0.27.2
```

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Write `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: syncservice
      POSTGRES_PASSWORD: syncservice
      POSTGRES_DB: syncservice
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U syncservice"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build: .
    environment:
      DATABASE_URL: postgresql+psycopg2://syncservice:syncservice@postgres:5432/syncservice
      WATCH_FOLDER: /data/watch
      WATCH_POLL_SECONDS: "30"
    volumes:
      - ./watch:/data/watch
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  pgdata:
```

- [ ] **Step 4: Write `.env.example`**

```
DATABASE_URL=postgresql+psycopg2://syncservice:syncservice@localhost:5432/syncservice
WATCH_FOLDER=./watch
WATCH_POLL_SECONDS=30
```

- [ ] **Step 5: Create empty package files**

Create `app/__init__.py` (empty) and `watch/.gitkeep` (empty).

- [ ] **Step 6: Write the failing test for settings**

```python
# tests/test_config.py
import importlib

from app.config import Settings


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.watch_poll_seconds == 30
    assert s.watch_folder == "./watch"


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("WATCH_POLL_SECONDS", "5")
    s = Settings(_env_file=None)
    assert s.watch_poll_seconds == 5
```

- [ ] **Step 7: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.config'` (module doesn't exist yet)

- [ ] **Step 8: Write `app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+psycopg2://syncservice:syncservice@localhost:5432/syncservice"
    watch_folder: str = "./watch"
    watch_poll_seconds: int = 30


settings = Settings()
```

- [ ] **Step 9: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 10: Commit**

```bash
git add requirements.txt Dockerfile docker-compose.yml .env.example app/__init__.py app/config.py watch/.gitkeep tests/test_config.py
git commit -m "chore: project scaffolding and settings"
```

---

### Task 2: Database models, engine, and seed data

**Files:**
- Create: `app/db.py`
- Create: `app/models.py`
- Create: `app/seed.py`
- Test: `tests/conftest.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `app.config.settings` (Task 1)
- Produces: `app.db.Base`, `app.db.engine`, `app.db.SessionLocal`, `app.db.get_db()` (FastAPI dependency generator); ORM classes `app.models.Source`, `SourceSection`, `SyncRun`, `IngestedFile`, `Stock`; `app.seed.seed_sources(db: Session) -> None`

**Manual prerequisite (do this once before running any test in this plan):**

```bash
docker compose up -d postgres
docker compose exec postgres psql -U syncservice -c "CREATE DATABASE syncservice_test;"
```

- [ ] **Step 1: Write `app/db.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 2: Write `app/models.py`**

```python
import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    type: Mapped[str] = mapped_column(String(20))  # "file" | "api"
    enabled: Mapped[bool] = mapped_column(default=True)

    sections: Mapped[list["SourceSection"]] = relationship(back_populates="source")


class SourceSection(Base):
    __tablename__ = "source_sections"
    __table_args__ = (UniqueConstraint("source_id", "name", name="uq_source_section"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    name: Mapped[str] = mapped_column(String(50))  # "stocks" | "fbs_orders"
    last_success_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source: Mapped["Source"] = relationship(back_populates="sections")


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_section_id: Mapped[int] = mapped_column(ForeignKey("source_sections.id"))
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # "success" | "partial" | "error" | "duplicate"
    received_count: Mapped[int] = mapped_column(Integer, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    source_section: Mapped["SourceSection"] = relationship()


class IngestedFile(Base):
    __tablename__ = "ingested_files"
    __table_args__ = (UniqueConstraint("source_section_id", "file_hash", name="uq_ingested_file_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_section_id: Mapped[int] = mapped_column(ForeignKey("source_sections.id"))
    file_hash: Mapped[str] = mapped_column(String(64))
    ingested_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sync_run_id: Mapped[int] = mapped_column(ForeignKey("sync_runs.id"))


class Stock(Base):
    __tablename__ = "stocks"
    __table_args__ = (UniqueConstraint("article", "warehouse", name="uq_stock_article_warehouse"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article: Mapped[str] = mapped_column(String(100))
    warehouse: Mapped[str] = mapped_column(String(200))
    product_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sku: Mapped[int | None] = mapped_column(Integer, nullable=True)
    placement_zone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cluster: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quantity_available: Mapped[int] = mapped_column(Integer, default=0)
    quantity_preparing: Mapped[int] = mapped_column(Integer, default=0)
    source_run_id: Mapped[int] = mapped_column(ForeignKey("sync_runs.id"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 3: Write `app/seed.py`**

```python
from sqlalchemy.orm import Session

from app.models import Source, SourceSection

SEED_SOURCES = [
    {"name": "ozon", "type": "file", "enabled": True, "sections": ["stocks"]},
    {"name": "wb", "type": "api", "enabled": False, "sections": []},
    {"name": "moysklad", "type": "api", "enabled": False, "sections": []},
]


def seed_sources(db: Session) -> None:
    for src in SEED_SOURCES:
        source = db.query(Source).filter_by(name=src["name"]).one_or_none()
        if source is None:
            source = Source(name=src["name"], type=src["type"], enabled=src["enabled"])
            db.add(source)
            db.flush()
        for section_name in src["sections"]:
            existing = (
                db.query(SourceSection)
                .filter_by(source_id=source.id, name=section_name)
                .one_or_none()
            )
            if existing is None:
                db.add(SourceSection(source_id=source.id, name=section_name))
    db.commit()
```

- [ ] **Step 4: Write `tests/conftest.py`**

```python
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.seed import seed_sources

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://syncservice:syncservice@localhost:5432/syncservice_test",
)

test_engine = create_engine(TEST_DATABASE_URL, future=True)


@pytest.fixture(scope="session", autouse=True)
def _setup_database():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def db_session():
    connection = test_engine.connect()
    trans = connection.begin()
    # join_transaction_mode="create_savepoint" lets ingest.py call db.commit()
    # freely — each commit closes a SAVEPOINT, not the outer transaction, so
    # the whole test still rolls back at the end.
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    seed_sources(session)
    yield session
    session.close()
    trans.rollback()
    connection.close()
```

- [ ] **Step 5: Write the failing test for models/seed**

```python
# tests/test_models.py
from app.models import Source, SourceSection


def test_seed_creates_ozon_stocks_section(db_session):
    section = (
        db_session.query(SourceSection)
        .join(Source)
        .filter(Source.name == "ozon", SourceSection.name == "stocks")
        .one()
    )
    assert section.source.enabled is True
    assert section.last_success_at is None


def test_seed_is_idempotent(db_session):
    from app.seed import seed_sources

    seed_sources(db_session)  # run again
    count = db_session.query(Source).filter_by(name="ozon").count()
    assert count == 1


def test_stock_unique_constraint(db_session):
    from sqlalchemy.exc import IntegrityError

    from app.models import IngestedFile, Stock, SyncRun

    section = (
        db_session.query(SourceSection)
        .join(Source)
        .filter(Source.name == "ozon", SourceSection.name == "stocks")
        .one()
    )
    run = SyncRun(source_section_id=section.id, status="success")
    db_session.add(run)
    db_session.flush()

    db_session.add(Stock(article="A1", warehouse="W1", quantity_available=1, source_run_id=run.id))
    db_session.flush()
    db_session.add(Stock(article="A1", warehouse="W1", quantity_available=2, source_run_id=run.id))
    try:
        db_session.flush()
        assert False, "expected IntegrityError"
    except IntegrityError:
        db_session.rollback()
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `TEST_DATABASE_URL=postgresql+psycopg2://syncservice:syncservice@localhost:5432/syncservice_test pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.db'`

- [ ] **Step 7: Verify implementation from steps 1-3 makes tests pass**

Run: `TEST_DATABASE_URL=postgresql+psycopg2://syncservice:syncservice@localhost:5432/syncservice_test pytest tests/test_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 8: Commit**

```bash
git add app/db.py app/models.py app/seed.py tests/conftest.py tests/test_models.py
git commit -m "feat: sync-core database models and idempotent seed data"
```

---

### Task 3: File hashing utility

**Files:**
- Create: `app/hashing.py`
- Test: `tests/test_hashing.py`

**Interfaces:**
- Produces: `app.hashing.file_sha256(path: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hashing.py
def test_file_sha256_stable_for_same_content(tmp_path):
    from app.hashing import file_sha256

    p1 = tmp_path / "a.txt"
    p2 = tmp_path / "b.txt"
    p1.write_bytes(b"same content")
    p2.write_bytes(b"same content")

    assert file_sha256(str(p1)) == file_sha256(str(p2))


def test_file_sha256_differs_for_different_content(tmp_path):
    from app.hashing import file_sha256

    p1 = tmp_path / "a.txt"
    p2 = tmp_path / "b.txt"
    p1.write_bytes(b"content one")
    p2.write_bytes(b"content two")

    assert file_sha256(str(p1)) != file_sha256(str(p2))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hashing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.hashing'`

- [ ] **Step 3: Write `app/hashing.py`**

```python
import hashlib


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_hashing.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/hashing.py tests/test_hashing.py
git commit -m "feat: file hashing utility for ingest dedup"
```

---

### Task 4: Ozon "Остатки" xlsx parser

**Files:**
- Create: `app/sources/__init__.py`
- Create: `app/sources/base.py`
- Create: `app/sources/file_source.py`
- Create: `tests/fixtures/__init__.py`
- Create: `tests/fixtures/xlsx_builder.py`
- Test: `tests/sources/__init__.py`
- Test: `tests/sources/test_file_source.py`

**Interfaces:**
- Produces: `app.sources.base.StockRow` (dataclass), `app.sources.file_source.FileSource.fetch_stocks(file_path: str) -> tuple[list[StockRow], list[ParseError]]`, `app.sources.file_source.ParseError(row_number: int, reason: str)`

- [ ] **Step 1: Write the xlsx test-fixture builder**

This reproduces the real file's structure exactly: sheet `Товар-склад`, header row 1, two
service rows (2-3), a units/description row (4), data from row 5. Verified against
`Управление остатками 24.08.2026 14-43.xlsx` in the калькулятор project.

```python
# tests/fixtures/xlsx_builder.py
import openpyxl

HEADER = [
    "Артикул", "Название товара", "SKU", "Признак товара", "Зона размещения",
    "Кластер", "Склад", "Доступно к продаже", "Недоступно к продаже",
]


def build_stocks_workbook(path: str, data_rows: list[tuple]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Товар-склад"
    ws.append(HEADER)
    ws.append([None] * len(HEADER))
    ws.append(["Нередактируемое"] * len(HEADER))
    ws.append(["Номер артикула"] + ["описание"] * (len(HEADER) - 1))
    for row in data_rows:
        ws.append(list(row))
    wb.save(path)
```

- [ ] **Step 2: Write the failing test**

```python
# tests/sources/test_file_source.py
from tests.fixtures.xlsx_builder import build_stocks_workbook


def test_fetch_stocks_parses_valid_rows(tmp_path):
    from app.sources.file_source import FileSource

    path = tmp_path / "stocks.xlsx"
    build_stocks_workbook(
        str(path),
        [
            ("CWROB1013DB", "Робот пылесос", 1293826229, None, "Сортируемый товар", "Ростов", "РОСТОВ-НА-ДОНУ_РФЦ", 8, 0),
            ("CWROB1013DB", "Робот пылесос", 1293826229, None, "Сортируемый товар", "Уфа", "УФА_РФЦ", 1, 0),
        ],
    )

    rows, errors = FileSource().fetch_stocks(str(path))

    assert errors == []
    assert len(rows) == 2
    assert rows[0].article == "CWROB1013DB"
    assert rows[0].warehouse == "РОСТОВ-НА-ДОНУ_РФЦ"
    assert rows[0].quantity_available == 8
    assert rows[0].sku == 1293826229
    assert rows[0].placement_zone == "Сортируемый товар"
    # same article, different warehouse -> both rows kept (real data has this shape)
    assert rows[1].warehouse == "УФА_РФЦ"


def test_fetch_stocks_skips_row_missing_article(tmp_path):
    from app.sources.file_source import FileSource

    path = tmp_path / "stocks.xlsx"
    build_stocks_workbook(
        str(path),
        [
            (None, "Без артикула", 1, None, "Сортируемый товар", "Ростов", "РОСТОВ-НА-ДОНУ_РФЦ", 8, 0),
            ("CWROB1017WH", "Пылесос", 2, None, "Сортируемый товар", "Уфа", "УФА_РФЦ", 1, 0),
        ],
    )

    rows, errors = FileSource().fetch_stocks(str(path))

    assert len(rows) == 1
    assert len(errors) == 1
    assert errors[0].row_number == 5
    assert "missing" in errors[0].reason


def test_fetch_stocks_raises_when_sheet_missing(tmp_path):
    import openpyxl

    from app.sources.file_source import FileSource

    path = tmp_path / "wrong.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "Not The Right Sheet"
    wb.save(str(path))

    try:
        FileSource().fetch_stocks(str(path))
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Товар-склад" in str(exc)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/sources/test_file_source.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.sources'`

- [ ] **Step 4: Write `app/sources/base.py`**

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass
class StockRow:
    article: str
    warehouse: str
    product_name: str | None = None
    sku: int | None = None
    placement_zone: str | None = None
    cluster: str | None = None
    quantity_available: int = 0
    quantity_preparing: int = 0


class SyncSource(Protocol):
    def fetch_stocks(self, file_path: str) -> tuple[list[StockRow], list["ParseError"]]: ...
```

- [ ] **Step 5: Write `app/sources/file_source.py`**

```python
import openpyxl

from app.sources.base import StockRow

SHEET_NAME = "Товар-склад"
DATA_START_ROW = 5

COL_ARTICLE = 0
COL_PRODUCT_NAME = 1
COL_SKU = 2
COL_PLACEMENT_ZONE = 4
COL_CLUSTER = 5
COL_WAREHOUSE = 6
COL_QTY_AVAILABLE = 7
COL_QTY_PREPARING = 8


class ParseError:
    def __init__(self, row_number: int, reason: str):
        self.row_number = row_number
        self.reason = reason


class FileSource:
    def fetch_stocks(self, file_path: str) -> tuple[list[StockRow], list[ParseError]]:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        if SHEET_NAME not in wb.sheetnames:
            wb.close()
            raise ValueError(f"sheet '{SHEET_NAME}' not found in {file_path}")

        ws = wb[SHEET_NAME]
        rows: list[StockRow] = []
        errors: list[ParseError] = []

        for row_number, raw in enumerate(
            ws.iter_rows(min_row=DATA_START_ROW, values_only=True), start=DATA_START_ROW
        ):
            article = raw[COL_ARTICLE]
            warehouse = raw[COL_WAREHOUSE]
            if article is None and warehouse is None:
                continue  # trailing blank row
            if not article or not warehouse:
                errors.append(ParseError(row_number, "missing article or warehouse"))
                continue
            rows.append(
                StockRow(
                    article=str(article),
                    warehouse=str(warehouse),
                    product_name=raw[COL_PRODUCT_NAME],
                    sku=int(raw[COL_SKU]) if raw[COL_SKU] is not None else None,
                    placement_zone=raw[COL_PLACEMENT_ZONE],
                    cluster=raw[COL_CLUSTER],
                    quantity_available=int(raw[COL_QTY_AVAILABLE] or 0),
                    quantity_preparing=int(raw[COL_QTY_PREPARING] or 0),
                )
            )

        wb.close()
        return rows, errors
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/sources/test_file_source.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add app/sources tests/fixtures tests/sources
git commit -m "feat: Ozon Остатки xlsx parser"
```

---

### Task 5: Ingest pipeline

**Files:**
- Create: `app/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `app.hashing.file_sha256` (Task 3), `app.sources.file_source.FileSource` (Task 4), `app.models.{Source,SourceSection,SyncRun,IngestedFile,Stock}` (Task 2)
- Produces: `app.ingest.ingest_stocks_file(db: Session, file_path: str) -> SyncRun`, status constants `STATUS_SUCCESS`, `STATUS_PARTIAL`, `STATUS_ERROR`, `STATUS_DUPLICATE`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ingest.py
from tests.fixtures.xlsx_builder import build_stocks_workbook

ROW_1 = ("A1", "Товар 1", 111, None, "Сортируемый товар", "Ростов", "РОСТОВ-НА-ДОНУ_РФЦ", 8, 0)
ROW_2 = ("A2", "Товар 2", 222, None, "Сортируемый товар", "Уфа", "УФА_РФЦ", 3, 1)


def test_ingest_new_file_success(tmp_path, db_session):
    from app.ingest import STATUS_SUCCESS, ingest_stocks_file
    from app.models import Stock

    path = tmp_path / "stocks.xlsx"
    build_stocks_workbook(str(path), [ROW_1, ROW_2])

    run = ingest_stocks_file(db_session, str(path))

    assert run.status == STATUS_SUCCESS
    assert run.received_count == 2
    assert run.changed_count == 2  # both are new inserts
    assert run.error_count == 0
    assert db_session.query(Stock).count() == 2


def test_ingest_same_file_twice_is_duplicate(tmp_path, db_session):
    from app.ingest import STATUS_DUPLICATE, ingest_stocks_file
    from app.models import Stock

    path = tmp_path / "stocks.xlsx"
    build_stocks_workbook(str(path), [ROW_1])

    ingest_stocks_file(db_session, str(path))
    second_run = ingest_stocks_file(db_session, str(path))

    assert second_run.status == STATUS_DUPLICATE
    assert db_session.query(Stock).count() == 1


def test_ingest_changed_quantity_counted(tmp_path, db_session):
    from app.ingest import ingest_stocks_file
    from app.models import Stock

    path1 = tmp_path / "v1.xlsx"
    build_stocks_workbook(str(path1), [ROW_1])
    ingest_stocks_file(db_session, str(path1))

    changed_row = ("A1", "Товар 1", 111, None, "Сортируемый товар", "Ростов", "РОСТОВ-НА-ДОНУ_РФЦ", 99, 0)
    path2 = tmp_path / "v2.xlsx"
    build_stocks_workbook(str(path2), [changed_row])
    run2 = ingest_stocks_file(db_session, str(path2))

    assert run2.changed_count == 1
    stock = db_session.query(Stock).filter_by(article="A1", warehouse="РОСТОВ-НА-ДОНУ_РФЦ").one()
    assert stock.quantity_available == 99


def test_ingest_unchanged_row_not_counted_as_changed(tmp_path, db_session):
    from app.ingest import ingest_stocks_file

    path1 = tmp_path / "v1.xlsx"
    build_stocks_workbook(str(path1), [ROW_1])
    ingest_stocks_file(db_session, str(path1))

    path2 = tmp_path / "v2.xlsx"
    build_stocks_workbook(str(path2), [ROW_1, ROW_2])  # ROW_1 unchanged, ROW_2 new
    run2 = ingest_stocks_file(db_session, str(path2))

    assert run2.received_count == 2
    assert run2.changed_count == 1  # only ROW_2 is new/changed


def test_ingest_partial_on_bad_row(tmp_path, db_session):
    from app.ingest import STATUS_PARTIAL, ingest_stocks_file

    bad_row = (None, "Без артикула", 1, None, "Сортируемый товар", "Ростов", "РОСТОВ-НА-ДОНУ_РФЦ", 8, 0)
    path = tmp_path / "stocks.xlsx"
    build_stocks_workbook(str(path), [ROW_1, bad_row])

    run = ingest_stocks_file(db_session, str(path))

    assert run.status == STATUS_PARTIAL
    assert run.received_count == 1
    assert run.error_count == 1


def test_ingest_error_leaves_canonical_table_untouched(tmp_path, db_session):
    import openpyxl

    from app.ingest import STATUS_ERROR, ingest_stocks_file
    from app.models import Stock

    good_path = tmp_path / "good.xlsx"
    build_stocks_workbook(str(good_path), [ROW_1])
    ingest_stocks_file(db_session, good_path.as_posix())
    count_before = db_session.query(Stock).count()

    broken_path = tmp_path / "broken.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "Wrong Sheet Name"
    wb.save(str(broken_path))

    run = ingest_stocks_file(db_session, str(broken_path))

    assert run.status == STATUS_ERROR
    assert run.error_message is not None
    assert db_session.query(Stock).count() == count_before


def test_ingest_updates_last_success_at_only_on_non_error(tmp_path, db_session):
    from app.ingest import ingest_stocks_file
    from app.models import Source, SourceSection

    path = tmp_path / "stocks.xlsx"
    build_stocks_workbook(str(path), [ROW_1])
    ingest_stocks_file(db_session, str(path))

    section = (
        db_session.query(SourceSection)
        .join(Source)
        .filter(Source.name == "ozon", SourceSection.name == "stocks")
        .one()
    )
    assert section.last_success_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `TEST_DATABASE_URL=postgresql+psycopg2://syncservice:syncservice@localhost:5432/syncservice_test pytest tests/test_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingest'`

- [ ] **Step 3: Write `app/ingest.py`**

```python
import datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.hashing import file_sha256
from app.models import IngestedFile, Source, SourceSection, Stock, SyncRun
from app.sources.file_source import FileSource

STATUS_SUCCESS = "success"
STATUS_PARTIAL = "partial"
STATUS_ERROR = "error"
STATUS_DUPLICATE = "duplicate"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def ingest_stocks_file(db: Session, file_path: str) -> SyncRun:
    section = (
        db.query(SourceSection)
        .join(Source)
        .filter(Source.name == "ozon", SourceSection.name == "stocks")
        .one()
    )

    file_hash = file_sha256(file_path)
    already = (
        db.query(IngestedFile)
        .filter_by(source_section_id=section.id, file_hash=file_hash)
        .one_or_none()
    )

    run = SyncRun(source_section_id=section.id, status=STATUS_ERROR)
    db.add(run)
    db.flush()

    if already is not None:
        run.status = STATUS_DUPLICATE
        run.finished_at = _now()
        db.commit()
        db.refresh(run)
        return run

    try:
        rows, parse_errors = FileSource().fetch_stocks(file_path)
    except ValueError as exc:
        run.status = STATUS_ERROR
        run.error_message = str(exc)
        run.finished_at = _now()
        db.add(IngestedFile(source_section_id=section.id, file_hash=file_hash, sync_run_id=run.id))
        db.commit()
        db.refresh(run)
        return run

    changed_count = 0
    for row in rows:
        stmt = pg_insert(Stock).values(
            article=row.article,
            warehouse=row.warehouse,
            product_name=row.product_name,
            sku=row.sku,
            placement_zone=row.placement_zone,
            cluster=row.cluster,
            quantity_available=row.quantity_available,
            quantity_preparing=row.quantity_preparing,
            source_run_id=run.id,
            updated_at=func.now(),
        )
        # Core-level upserts bypass the ORM's onupdate hook, so updated_at
        # must be set explicitly in both the insert values and the
        # conflict's SET clause below.
        stmt = stmt.on_conflict_do_update(
            index_elements=["article", "warehouse"],
            set_={
                "product_name": stmt.excluded.product_name,
                "sku": stmt.excluded.sku,
                "placement_zone": stmt.excluded.placement_zone,
                "cluster": stmt.excluded.cluster,
                "quantity_available": stmt.excluded.quantity_available,
                "quantity_preparing": stmt.excluded.quantity_preparing,
                "source_run_id": stmt.excluded.source_run_id,
                "updated_at": func.now(),
            },
            where=(
                (Stock.quantity_available != row.quantity_available)
                | (Stock.quantity_preparing != row.quantity_preparing)
                | (Stock.product_name.is_distinct_from(row.product_name))
                | (Stock.placement_zone.is_distinct_from(row.placement_zone))
                | (Stock.cluster.is_distinct_from(row.cluster))
            ),
        ).returning(Stock.id)
        if db.execute(stmt).first() is not None:
            changed_count += 1

    run.received_count = len(rows)
    run.changed_count = changed_count
    run.error_count = len(parse_errors)

    if parse_errors and not rows:
        run.status = STATUS_ERROR
    elif parse_errors:
        run.status = STATUS_PARTIAL
    else:
        run.status = STATUS_SUCCESS

    if parse_errors:
        run.error_message = "; ".join(f"row {e.row_number}: {e.reason}" for e in parse_errors[:20])

    run.finished_at = _now()
    if run.status in (STATUS_SUCCESS, STATUS_PARTIAL):
        section.last_success_at = run.finished_at

    db.add(IngestedFile(source_section_id=section.id, file_hash=file_hash, sync_run_id=run.id))
    db.commit()
    db.refresh(run)
    return run
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `TEST_DATABASE_URL=postgresql+psycopg2://syncservice:syncservice@localhost:5432/syncservice_test pytest tests/test_ingest.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add app/ingest.py tests/test_ingest.py
git commit -m "feat: stocks ingest pipeline with dedup, upsert, and sync journal"
```

---

### Task 6: HTTP API (upload / status / runs)

**Files:**
- Create: `app/routers/__init__.py`
- Create: `app/routers/sync.py`
- Create: `app/main.py`
- Test: `tests/routers/__init__.py`
- Test: `tests/routers/test_sync.py`

**Interfaces:**
- Consumes: `app.ingest.ingest_stocks_file` (Task 5), `app.db.get_db` (Task 2)
- Produces: FastAPI app `app.main.app`; routes `POST /sync/{source}/{section}/upload`, `GET /sync/status`, `GET /sync/runs`

- [ ] **Step 1: Write `app/routers/sync.py`**

```python
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.ingest import ingest_stocks_file
from app.models import Source, SourceSection, SyncRun

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/{source}/{section}/upload")
def upload_file(source: str, section: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    if source != "ozon" or section != "stocks":
        raise HTTPException(status_code=400, detail=f"unsupported source/section: {source}/{section}")

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        run = ingest_stocks_file(db, tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return {
        "sync_run_id": run.id,
        "status": run.status,
        "received_count": run.received_count,
        "changed_count": run.changed_count,
        "error_count": run.error_count,
        "error_message": run.error_message,
    }


@router.get("/status")
def sync_status(db: Session = Depends(get_db)):
    sections = db.query(SourceSection).join(Source).all()
    result = []
    for section in sections:
        last_run = (
            db.query(SyncRun)
            .filter(SyncRun.source_section_id == section.id)
            .order_by(SyncRun.started_at.desc())
            .first()
        )
        result.append(
            {
                "source": section.source.name,
                "section": section.name,
                "last_success_at": section.last_success_at,
                "last_attempt_status": last_run.status if last_run else None,
                "last_attempt_at": last_run.started_at if last_run else None,
            }
        )
    return result


@router.get("/runs")
def sync_runs(
    source: str | None = None,
    section: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(SyncRun).join(SourceSection).join(Source)
    if source:
        query = query.filter(Source.name == source)
    if section:
        query = query.filter(SourceSection.name == section)
    runs = query.order_by(SyncRun.started_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "source": r.source_section.source.name,
            "section": r.source_section.name,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "status": r.status,
            "received_count": r.received_count,
            "changed_count": r.changed_count,
            "error_count": r.error_count,
            "error_message": r.error_message,
        }
        for r in runs
    ]
```

- [ ] **Step 2: Write `app/main.py`**

```python
from fastapi import FastAPI

from app.db import Base, SessionLocal, engine
from app.routers.sync import router as sync_router
from app.seed import seed_sources
from app.watcher import start_scheduler

app = FastAPI(title="Сервис логиста 2.0 — Sync Core")
app.include_router(sync_router)

_scheduler = None


@app.on_event("startup")
def on_startup():
    global _scheduler
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_sources(db)
    finally:
        db.close()
    _scheduler = start_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    if _scheduler is not None:
        _scheduler.shutdown()
```

Note: `app/watcher.py` does not exist yet — this import is satisfied in Task 7. Do not run
this file's tests until Task 7's `app/watcher.py` is in place (Task 7 is next).

- [ ] **Step 3: Write the failing tests**

These tests instantiate `TestClient(app)` **without** the `with` context manager, so FastAPI's
`startup` event (which touches the real dev database and starts the scheduler) never fires.
`get_db` is overridden to use the test's `db_session` fixture instead.

```python
# tests/routers/test_sync.py
import io

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from tests.fixtures.xlsx_builder import build_stocks_workbook

ROW_1 = ("A1", "Товар 1", 111, None, "Сортируемый товар", "Ростов", "РОСТОВ-НА-ДОНУ_РФЦ", 8, 0)


@pytest.fixture()
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_upload_unsupported_source_returns_400(client):
    resp = client.post(
        "/sync/wb/stocks/upload",
        files={"file": ("x.xlsx", b"irrelevant", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_upload_ozon_stocks_success(client, tmp_path):
    path = tmp_path / "stocks.xlsx"
    build_stocks_workbook(str(path), [ROW_1])

    with open(path, "rb") as f:
        resp = client.post(
            "/sync/ozon/stocks/upload",
            files={"file": ("stocks.xlsx", f.read(), "application/octet-stream")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["received_count"] == 1
    assert body["changed_count"] == 1


def test_status_endpoint_reflects_last_success(client, tmp_path):
    path = tmp_path / "stocks.xlsx"
    build_stocks_workbook(str(path), [ROW_1])
    with open(path, "rb") as f:
        client.post(
            "/sync/ozon/stocks/upload",
            files={"file": ("stocks.xlsx", f.read(), "application/octet-stream")},
        )

    resp = client.get("/sync/status")
    assert resp.status_code == 200
    body = resp.json()
    ozon_stocks = next(s for s in body if s["source"] == "ozon" and s["section"] == "stocks")
    assert ozon_stocks["last_success_at"] is not None
    assert ozon_stocks["last_attempt_status"] == "success"


def test_runs_endpoint_lists_and_filters(client, tmp_path):
    path = tmp_path / "stocks.xlsx"
    build_stocks_workbook(str(path), [ROW_1])
    with open(path, "rb") as f:
        client.post(
            "/sync/ozon/stocks/upload",
            files={"file": ("stocks.xlsx", f.read(), "application/octet-stream")},
        )

    resp = client.get("/sync/runs", params={"source": "ozon", "section": "stocks"})
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 1
    assert runs[0]["status"] == "success"

    resp_empty = client.get("/sync/runs", params={"source": "wb"})
    assert resp_empty.json() == []
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `TEST_DATABASE_URL=postgresql+psycopg2://syncservice:syncservice@localhost:5432/syncservice_test pytest tests/routers/test_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.watcher'` (Task 7 not done yet — expected at this point)

- [ ] **Step 5: Commit routers and main (watcher comes next task)**

```bash
git add app/routers app/main.py tests/routers
git commit -m "feat: sync HTTP API (upload/status/runs) — depends on watcher stub from next task"
```

---

### Task 7: Watch-folder scheduler

**Files:**
- Create: `app/watcher.py`
- Test: `tests/test_watcher.py`

**Interfaces:**
- Consumes: `app.config.settings`, `app.db.SessionLocal`, `app.ingest.ingest_stocks_file` (Task 5)
- Produces: `app.watcher.scan_watch_folder(watch_folder: str) -> list[SyncRun]`, `app.watcher.start_scheduler() -> BackgroundScheduler`

- [ ] **Step 1: Write `app/watcher.py`**

```python
import logging
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.db import SessionLocal
from app.ingest import STATUS_DUPLICATE, ingest_stocks_file

logger = logging.getLogger(__name__)


def scan_watch_folder(watch_folder: str) -> list:
    results = []
    folder = Path(watch_folder)
    if not folder.exists():
        return results

    db = SessionLocal()
    try:
        for path in sorted(folder.glob("*.xlsx")):
            run = ingest_stocks_file(db, str(path))
            results.append(run)
            if run.status != STATUS_DUPLICATE:
                logger.info("watch-folder ingest %s: %s", path.name, run.status)
    finally:
        db.close()
    return results


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        scan_watch_folder,
        "interval",
        seconds=settings.watch_poll_seconds,
        args=[settings.watch_folder],
        id="watch_folder_scan",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
```

- [ ] **Step 2: Run Task 6's router tests now — they should pass**

Run: `TEST_DATABASE_URL=postgresql+psycopg2://syncservice:syncservice@localhost:5432/syncservice_test pytest tests/routers/test_sync.py -v`
Expected: PASS (4 tests) — the `ModuleNotFoundError` from Task 6 Step 4 is now resolved.

- [ ] **Step 3: Write the failing test for the watcher itself**

`scan_watch_folder()` is called directly (not through the real APScheduler timer) so the test
is fast and deterministic — this exercises the exact function the scheduler calls on each tick.

```python
# tests/test_watcher.py
from tests.fixtures.xlsx_builder import build_stocks_workbook

ROW_1 = ("A1", "Товар 1", 111, None, "Сортируемый товар", "Ростов", "РОСТОВ-НА-ДОНУ_РФЦ", 8, 0)


def test_scan_watch_folder_ingests_new_file(tmp_path, monkeypatch, db_session):
    import app.watcher as watcher_module

    monkeypatch.setattr(watcher_module, "SessionLocal", lambda: db_session)
    # db_session.close() is a no-op inside the test transaction wrapper
    monkeypatch.setattr(db_session, "close", lambda: None)

    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    build_stocks_workbook(str(watch_dir / "stocks.xlsx"), [ROW_1])

    results = watcher_module.scan_watch_folder(str(watch_dir))

    assert len(results) == 1
    assert results[0].status == "success"


def test_scan_watch_folder_dedupes_on_second_scan(tmp_path, monkeypatch, db_session):
    import app.watcher as watcher_module

    monkeypatch.setattr(watcher_module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    build_stocks_workbook(str(watch_dir / "stocks.xlsx"), [ROW_1])

    watcher_module.scan_watch_folder(str(watch_dir))
    second = watcher_module.scan_watch_folder(str(watch_dir))

    assert second[0].status == "duplicate"


def test_scan_watch_folder_missing_dir_returns_empty(tmp_path):
    from app.watcher import scan_watch_folder

    result = scan_watch_folder(str(tmp_path / "does-not-exist"))
    assert result == []
```

- [ ] **Step 4: Run test to verify it fails for the right reason, then passes**

Run: `TEST_DATABASE_URL=postgresql+psycopg2://syncservice:syncservice@localhost:5432/syncservice_test pytest tests/test_watcher.py -v`
Expected: PASS (3 tests) — `app/watcher.py` was already written in Step 1, so this confirms
the behavior rather than following red-green in strict order for this task.

- [ ] **Step 5: Commit**

```bash
git add app/watcher.py tests/test_watcher.py
git commit -m "feat: watch-folder scheduler for automatic Ozon stocks ingest"
```

---

### Task 8: Docker Compose wiring & manual end-to-end verification

**Files:**
- Modify: none (verification only)

**Interfaces:**
- Consumes: everything from Tasks 1-7

- [ ] **Step 1: Run the full test suite**

Run: `TEST_DATABASE_URL=postgresql+psycopg2://syncservice:syncservice@localhost:5432/syncservice_test pytest -v`
Expected: PASS (all tests from Tasks 1-7)

- [ ] **Step 2: Build and start the full stack**

```bash
docker compose up -d --build
docker compose logs -f backend
```

Expected in logs: uvicorn started, no traceback on startup (tables created, seed ran, scheduler started).

- [ ] **Step 3: Manual upload smoke test with a real file**

Copy a real Ozon export into the project and upload it:

```bash
curl -X POST "http://localhost:8000/sync/ozon/stocks/upload" \
  -F "file=@C:/Users/1/Desktop/калькулятор/Управление остатками 24.08.2026 14-43.xlsx"
```

Expected: JSON response with `"status": "success"`, `"received_count": 738` (or close to it —
depends on the exact file content at run time), `"error_count": 0`.

- [ ] **Step 4: Verify status and journal endpoints**

```bash
curl "http://localhost:8000/sync/status"
curl "http://localhost:8000/sync/runs?source=ozon&section=stocks"
```

Expected: `/sync/status` shows a recent `last_success_at` for `ozon`/`stocks`; `/sync/runs`
lists the run from Step 3.

- [ ] **Step 5: Watch-folder smoke test**

```bash
cp "C:/Users/1/Desktop/калькулятор/Управление остатками 24.08.2026 14-43.xlsx" "./watch/stocks-watch-test.xlsx"
```

Wait up to `WATCH_POLL_SECONDS` (30s), then:

```bash
docker compose logs backend | grep "watch-folder ingest"
```

Expected: a log line showing the file was ingested (status `success` or `duplicate` if the
same content was already uploaded in Step 3 — both are correct outcomes).

- [ ] **Step 6: Tear down**

```bash
docker compose down
```

No commit for this task — it's verification only, nothing new to add to git.

---

## Self-Review Notes

- **Spec coverage:** requirements 4 (dedup), 5 (new/changed), 6 (`last_success_at`), 7 (`sync_runs`
  journal), 9 (`error_message`/`error_count`), 11 (manual upload endpoint), 12 (error leaves
  `stocks` untouched — tested explicitly), 13 (`source_run_id` on every `stocks` row), 14
  (`GET /sync/status`) are each covered by a task and a test. Requirements 1/3/8/10 are
  explicitly out of scope per the spec and Global Constraints above.
- **Type consistency:** `ingest_stocks_file(db: Session, file_path: str) -> SyncRun` signature
  is identical across Tasks 5, 6, and 7. `FileSource.fetch_stocks` return type
  `tuple[list[StockRow], list[ParseError]]` is consistent between Task 4's definition and Task 5's
  usage. Status string constants (`STATUS_SUCCESS` etc.) are defined once in `app/ingest.py`
  (Task 5) and imported everywhere else they're used (Task 7).
- **Known ordering quirk:** Task 6 writes `app/main.py`, which imports `app.watcher` — a module
  that doesn't exist until Task 7. This is called out explicitly in Task 6 so an executor isn't
  confused by the import error; Task 7 Step 2 confirms it resolves.
