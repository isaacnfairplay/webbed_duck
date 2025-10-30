"""Shared utilities for server-side UI rendering."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pyarrow as pa


def table_to_records(table: pa.Table) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in table.to_pylist():
        converted = {key: json_friendly(value) for key, value in row.items()}
        records.append(converted)
    return records


def json_friendly(value: object) -> object:
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f") if value.is_finite() else str(value)
    return value


__all__ = ["table_to_records", "json_friendly"]
