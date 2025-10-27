from pathlib import Path
import sqlite3

from webbed_duck.server.meta import MetaStore


def test_metastore_adds_redaction_column(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    runtime = storage_root / "runtime"
    runtime.mkdir(parents=True)
    db_path = runtime / "meta.sqlite3"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE shares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL UNIQUE,
                route_id TEXT NOT NULL,
                params_json TEXT NOT NULL,
                format TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_by_hash TEXT,
                user_agent_hash TEXT,
                ip_prefix TEXT
            );
            """
        )
        conn.commit()

    store = MetaStore(storage_root)

    with store.connect() as conn:
        names = [row["name"] for row in conn.execute("PRAGMA table_info(shares)")]

    assert "redact_columns_json" in names
