"""SQLite-backed metadata store for sessions, shares, and analytics."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping, Sequence


_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_hash TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL,
        email_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        user_agent_hash TEXT,
        ip_prefix TEXT
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sessions_expires
    ON sessions (expires_at);
    """,
    """
    CREATE TABLE IF NOT EXISTS shares (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_hash TEXT NOT NULL UNIQUE,
        route_id TEXT NOT NULL,
        params_json TEXT NOT NULL,
        format TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_by_hash TEXT,
        user_agent_hash TEXT,
        ip_prefix TEXT,
        redact_columns_json TEXT
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_shares_expires
    ON shares (expires_at);
    """,
)


@dataclass(slots=True)
class SessionRecord:
    token: str
    email: str
    email_hash: str
    expires_at: datetime


@dataclass(slots=True)
class ShareRecord:
    route_id: str
    params: Mapping[str, object]
    format: str
    expires_at: datetime
    redact_columns: Sequence[str]


class MetaStore:
    """Manage the SQLite database under ``runtime/meta.sqlite3``."""

    def __init__(self, storage_root: Path) -> None:
        runtime = Path(storage_root) / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        self._path = runtime / "meta.sqlite3"
        self._lock = threading.Lock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.connect() as conn:
            for statement in _SCHEMA:
                conn.execute(statement)
            _ensure_share_redaction_columns(conn)
            conn.commit()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(self._path)
        try:
            conn.row_factory = sqlite3.Row
            yield conn
        finally:
            conn.close()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def serialize_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def deserialize_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _ensure_share_redaction_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(shares)")}
    if "redact_columns_json" not in existing:
        conn.execute("ALTER TABLE shares ADD COLUMN redact_columns_json TEXT")


__all__ = [
    "MetaStore",
    "SessionRecord",
    "ShareRecord",
    "serialize_datetime",
    "deserialize_datetime",
    "_utcnow",
]
