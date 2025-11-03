"""Shared DuckDB utilities for the test-suite."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Iterator, Tuple

import duckdb

DEFAULT_DB_NAME = "webbed_duck_test.duckdb"


def database_path(tmp_path_factory, *, prefix: str = "duckdb") -> Path:
    """Return the filesystem path for a temporary DuckDB database."""

    base = tmp_path_factory.mktemp(prefix)
    return Path(base) / DEFAULT_DB_NAME


@contextlib.contextmanager
def temporary_database(tmp_path_factory, *, prefix: str = "duckdb") -> Iterator[Tuple[duckdb.DuckDBPyConnection, Path]]:
    """Yield a DuckDB connection and the backing file path, cleaning up afterwards."""

    path = database_path(tmp_path_factory, prefix=prefix)
    connection = duckdb.connect(str(path))
    try:
        yield connection, path
    finally:
        connection.close()
        if path.exists():
            path.unlink()


def configure_test_connection(connection: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """Apply pragmatic defaults to a DuckDB connection for deterministic tests."""

    temp_dir = Path.cwd() / "tmp_duckdb"
    temp_dir.mkdir(exist_ok=True)
    connection.execute("PRAGMA threads=2")
    connection.execute("PRAGMA memory_limit='1024MB'")
    connection.execute("PRAGMA temp_directory=?", [str(temp_dir)])
    return connection
