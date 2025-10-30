from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence

import pyarrow as pa


@dataclass(slots=True)
class OverrideRecord:
    """A stored override for a single cell identified by ``row_key``."""

    route_id: str
    row_key: str
    column: str
    value: Any
    reason: str | None
    author_hash: str | None
    author_user_id: str | None
    created_ts: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_ts"] = round(self.created_ts, 6)
        return payload


class OverlayStore:
    """Persist per-cell overrides under the configured storage root."""

    def __init__(
        self,
        storage_root: Path,
        *,
        time_fn: Callable[[], float] | None = None,
        hash_fn: Callable[[str], str] | None = None,
    ) -> None:
        self._path = Path(storage_root) / "runtime" / "overrides.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data: MutableMapping[str, list[dict[str, Any]]] = self._load()
        self._time_fn = time_fn or time.time
        self._hash_fn = hash_fn or _hash_author

    def list_for_route(self, route_id: str) -> list[OverrideRecord]:
        with self._lock:
            raw = list(self._data.get(route_id, ()))
        records: list[OverrideRecord] = []
        for item in raw:
            data = dict(item)
            data.setdefault("route_id", route_id)
            data.setdefault("author_hash", None)
            data.setdefault("author_user_id", None)
            data.setdefault("reason", None)
            records.append(OverrideRecord(**data))
        return records

    def count_for_route(self, route_id: str) -> int:
        with self._lock:
            bucket = self._data.get(route_id)
            return len(bucket) if bucket else 0

    def upsert(
        self,
        *,
        route_id: str,
        row_key: str,
        column: str,
        value: Any,
        reason: str | None = None,
        author: str | None = None,
        author_user_id: str | None = None,
    ) -> OverrideRecord:
        record = OverrideRecord(
            route_id=route_id,
            row_key=row_key,
            column=column,
            value=value,
            reason=reason,
            author_hash=self._hash_fn(author) if author else None,
            author_user_id=author_user_id,
            created_ts=self._time_fn(),
        )
        payload = record.to_dict()
        with self._lock:
            bucket = self._data.setdefault(route_id, [])
            replaced = False
            for index, item in enumerate(bucket):
                if item["row_key"] == row_key and item["column"] == column:
                    bucket[index] = payload
                    replaced = True
                    break
            if not replaced:
                bucket.append(payload)
            self._save()
        return record

    def remove(self, route_id: str, row_key: str, column: str) -> bool:
        with self._lock:
            bucket = self._data.get(route_id)
            if not bucket:
                return False
            original = len(bucket)
            bucket[:] = [item for item in bucket if not (item["row_key"] == row_key and item["column"] == column)]
            changed = len(bucket) != original
            if changed:
                self._save()
            return changed

    def reload(self) -> None:
        """Reload overlay data from disk, replacing the in-memory snapshot."""

        with self._lock:
            self._data = self._load()

    def _load(self) -> MutableMapping[str, list[dict[str, Any]]]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        filtered: MutableMapping[str, list[dict[str, Any]]] = {}
        for route_id, items in data.items():
            if not isinstance(items, list):
                continue
            filtered[str(route_id)] = [item for item in items if isinstance(item, dict)]
        return filtered

    def _save(self) -> None:
        self._path.write_text(json.dumps(self._data, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")


def apply_overrides(
    table: pa.Table,
    metadata: Mapping[str, Any] | None,
    overrides: Iterable[OverrideRecord],
) -> pa.Table:
    override_meta = metadata.get("overrides", {}) if isinstance(metadata, Mapping) else {}
    key_columns = _coerce_sequence(override_meta.get("key_columns"))
    allowed = set(_coerce_sequence(override_meta.get("allowed")))
    if allowed:
        applicable = [record for record in overrides if record.column in allowed]
    else:
        applicable = list(overrides)
    if not applicable:
        return table

    records = table.to_pylist()
    schema = table.schema
    field_types = {field.name: field.type for field in schema}
    override_map: dict[str, dict[str, Any]] = {}
    for record in applicable:
        override_map.setdefault(record.row_key, {})[record.column] = record.value

    for row in records:
        row_key = compute_row_key(row, key_columns, table.column_names)
        updates = override_map.get(row_key)
        if not updates:
            continue
        for column, value in updates.items():
            field_type = field_types.get(column)
            if field_type is not None:
                try:
                    value = pa.array([value], type=field_type)[0].as_py()
                except (pa.ArrowInvalid, pa.ArrowTypeError):
                    value = value
            row[column] = value

    return pa.Table.from_pylist(records, schema=schema)


def compute_row_key(
    row: Mapping[str, Any],
    key_columns: Sequence[str] | None,
    available_columns: Sequence[str] | None = None,
) -> str:
    if key_columns:
        payload = {name: row.get(name) for name in key_columns}
    else:
        payload = {name: row.get(name) for name in (available_columns or row.keys())}
    return json.dumps(payload, sort_keys=True, default=_json_default)


def compute_row_key_from_values(values: Mapping[str, Any], key_columns: Sequence[str] | None) -> str:
    if key_columns:
        missing = [name for name in key_columns if name not in values]
        if missing:
            raise KeyError(f"Missing key values for columns: {', '.join(missing)}")
        payload = {name: values[name] for name in key_columns}
    else:
        payload = dict(values)
    return json.dumps(payload, sort_keys=True, default=_json_default)


def _coerce_sequence(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item) for item in value]
    return []


def _hash_author(author: str) -> str:
    normalized = author.strip().lower().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # pragma: no cover - fallback for unexpected objects
            return str(value)
    return value


__all__ = [
    "OverrideRecord",
    "OverlayStore",
    "apply_overrides",
    "compute_row_key",
    "compute_row_key_from_values",
]
