import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS watch_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marketplace TEXT NOT NULL,
    cabinet_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    reference_json TEXT NOT NULL,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    max_coefficient INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'watching',
    requested_by_chat_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marketplace TEXT NOT NULL,
    cabinet_id INTEGER NOT NULL,
    order_key TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    UNIQUE(marketplace, cabinet_id, order_key, alert_type)
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def create_watch_request(
    conn: sqlite3.Connection,
    *,
    marketplace: str,
    cabinet_id: int,
    kind: str,
    reference_json: str,
    date_from: str,
    date_to: str,
    max_coefficient: int,
    requested_by_chat_id: int,
    now: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO watch_requests (
            marketplace, cabinet_id, kind, reference_json, date_from, date_to,
            max_coefficient, status, requested_by_chat_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'watching', ?, ?, ?)
        """,
        (
            marketplace, cabinet_id, kind, reference_json, date_from, date_to,
            max_coefficient, requested_by_chat_id, now, now,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def list_watch_requests(conn: sqlite3.Connection, *, status: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM watch_requests WHERE status = ? ORDER BY id", (status,)
    ).fetchall()


def update_watch_status(conn: sqlite3.Connection, watch_id: int, status: str, now: str) -> None:
    conn.execute(
        "UPDATE watch_requests SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, watch_id),
    )
    conn.commit()


def record_alert(
    conn: sqlite3.Connection,
    *,
    marketplace: str,
    cabinet_id: int,
    order_key: str,
    alert_type: str,
    now: str,
) -> bool:
    try:
        conn.execute(
            """
            INSERT INTO alert_log (marketplace, cabinet_id, order_key, alert_type, sent_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (marketplace, cabinet_id, order_key, alert_type, now),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
