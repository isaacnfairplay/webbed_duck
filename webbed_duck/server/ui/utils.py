"""Shared utilities for server-side UI rendering."""
from __future__ import annotations

import datetime as dt

import pyarrow as pa


def table_to_records(table: pa.Table) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in table.to_pylist():
        converted = {key: json_friendly(value) for key, value in row.items()}
        records.append(converted)
    return records


def json_friendly(value: object) -> object:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


__all__ = ["table_to_records", "json_friendly"]
