from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pytest

from webbed_duck.server.overlay import (
    OverlayStore,
    OverrideRecord,
    apply_overrides,
    compute_row_key,
    compute_row_key_from_values,
)


class _TimeStub:
    def __init__(self, start: float = 100.0) -> None:
        self.value = start

    def __call__(self) -> float:
        self.value += 1.0
        return self.value


def test_overlay_store_upsert_list_and_remove(tmp_path: Path) -> None:
    time_stub = _TimeStub()
    hashes: list[str] = []

    def _hash(value: str) -> str:
        hashes.append(value)
        return f"hash:{value}"

    store = OverlayStore(tmp_path, time_fn=time_stub, hash_fn=_hash)

    first = store.upsert(
        route_id="demo",
        row_key="{\"id\": 1}",
        column="status",
        value="draft",
        reason="initial",
        author="Alice",
        author_user_id="user-1",
    )

    assert first.author_hash == "hash:Alice"
    assert pytest.approx(101.0) == first.created_ts
    assert hashes == ["Alice"]
    assert store.count_for_route("demo") == 1

    second = store.upsert(
        route_id="demo",
        row_key="{\"id\": 1}",
        column="status",
        value="published",
        reason="update",
        author="Bob",
    )

    assert second.value == "published"
    assert pytest.approx(102.0) == second.created_ts
    assert hashes == ["Alice", "Bob"]

    records = store.list_for_route("demo")
    assert len(records) == 1
    assert records[0].value == "published"
    assert records[0].reason == "update"
    assert records[0].author_hash == "hash:Bob"
    assert records[0].author_user_id is None

    payload_path = tmp_path / "runtime" / "overrides.json"
    saved = json.loads(payload_path.read_text(encoding="utf-8"))
    assert "demo" in saved
    assert len(saved["demo"]) == 1
    payload = saved["demo"][0]
    assert payload["route_id"] == "demo"
    assert payload["row_key"] == "{\"id\": 1}"
    assert payload["column"] == "status"
    assert payload["value"] == "published"
    assert payload["reason"] == "update"
    assert payload["author_hash"] == "hash:Bob"
    assert payload["author_user_id"] is None
    assert payload["created_ts"] == pytest.approx(records[0].created_ts, rel=1e-6)

    assert store.remove("demo", "{\"id\": 1}", "status") is True
    assert store.count_for_route("demo") == 0
    assert store.remove("demo", "{\"id\": 1}", "status") is False


def test_apply_overrides_respects_allowed_columns_and_types() -> None:
    table = pa.table({"id": [1], "value": pa.array([5], type=pa.int64()), "note": ["keep"]})
    row_key = compute_row_key_from_values({"id": 1}, ["id"])
    records = [
        OverrideRecord(
            route_id="demo",
            row_key=row_key,
            column="value",
            value=7,
            reason=None,
            author_hash=None,
            author_user_id=None,
            created_ts=0.0,
        ),
        OverrideRecord(
            route_id="demo",
            row_key=row_key,
            column="note",
            value="ignore",
            reason=None,
            author_hash=None,
            author_user_id=None,
            created_ts=0.0,
        ),
    ]

    metadata = {"overrides": {"key_columns": ["id"], "allowed": ["value"]}}
    updated = apply_overrides(table, metadata, records)

    assert updated.column("value")[0].as_py() == 7
    assert updated.column("note")[0].as_py() == "keep"

    # When allowed list is empty the remaining overrides apply.
    updated_all = apply_overrides(table, {"overrides": {"key_columns": ["id"]}}, records)
    assert updated_all.column("note")[0].as_py() == "ignore"


def test_row_key_helpers_require_expected_columns() -> None:
    row = {"id": 5, "slug": "alpha"}
    key = compute_row_key(row, ["id"])
    assert json.loads(key) == {"id": 5}

    auto_key = compute_row_key(row, None, available_columns=["slug", "id"])
    assert json.loads(auto_key) == {"id": 5, "slug": "alpha"}

    with pytest.raises(KeyError):
        compute_row_key_from_values({"id": 7}, ["id", "slug"])
