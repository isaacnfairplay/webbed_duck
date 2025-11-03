from __future__ import annotations

import base64
import hashlib
import json
import shutil
import time
from dataclasses import dataclass, field, replace
import decimal
import math
from itertools import product
from pathlib import Path
from typing import Callable, Mapping, Sequence

import duckdb
import pyarrow as pa
import pyarrow.ipc as paipc
import pyarrow.parquet as pq
import pyarrow.compute as pc

from ..config import CacheConfig
from ..core.routes import RouteDefinition


RecordBatchFactory = Callable[[], tuple[pa.RecordBatchReader, Callable[[], None]]]


@dataclass(slots=True)
class CacheSettings:
    """Resolved caching behaviour for a route."""

    enabled: bool
    ttl_seconds: int
    rows_per_page: int
    enforce_page_size: bool
    invariant_filters: tuple["InvariantFilterSetting", ...] = ()
    order_by: tuple[str, ...] = ()


@dataclass(slots=True)
class InvariantFilterSetting:
    """Describe a parameter whose filtering can be applied post-cache."""

    param: str
    column: str
    separator: str | None = None
    case_insensitive: bool = False
    extra: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class CacheKey:
    route_id: str
    digest: str

    def path(self, root: Path) -> Path:
        return Path(root) / self.route_id / self.digest


@dataclass(slots=True)
class CacheReadResult:
    table: pa.Table
    total_rows: int
    applied_offset: int
    applied_limit: int | None
    from_cache: bool
    meta: Mapping[str, object] | None = None


@dataclass(slots=True)
class CacheQueryResult:
    table: pa.Table
    total_rows: int
    applied_offset: int
    applied_limit: int | None
    used_cache: bool
    cache_hit: bool
    meta: Mapping[str, object] | None = None


@dataclass(slots=True)
class CacheArtifactResult:
    paths: tuple[Path, ...]
    schema: pa.Schema
    total_rows: int
    cache_key: CacheKey


class CacheStore:
    """Persist and reuse paged query results."""

    def __init__(self, storage_root: Path) -> None:
        root = Path(storage_root).expanduser()
        try:
            root = root.resolve(strict=False)
        except RuntimeError:  # pragma: no cover - defensive on exotic path objects
            root = Path(root)
        self._root = root / "cache"
        self._root.mkdir(parents=True, exist_ok=True)

    def compute_key(
        self,
        route: RouteDefinition,
        params: Mapping[str, object],
        settings: CacheSettings,
    ) -> CacheKey:
        payload = {
            "route": route.id,
            "version": route.version,
            "sql": route.prepared_sql,
            "rows_per_page": settings.rows_per_page,
            "order_by": list(settings.order_by),
            "params": _normalize_mapping(params),
            "invariants": [
                {
                    "param": setting.param,
                    "column": setting.column,
                    "separator": setting.separator,
                    "case_insensitive": setting.case_insensitive,
                }
                for setting in _sorted_invariant_filters(settings.invariant_filters)
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, default=_json_default).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        return CacheKey(route_id=route.id, digest=digest)

    def get_or_populate(
        self,
        key: CacheKey,
        *,
        route_signature: str,
        settings: CacheSettings,
        offset: int,
        limit: int | None,
        reader_factory: RecordBatchFactory,
        invariant_values: Mapping[str, Sequence[object]] | None = None,
    ) -> CacheReadResult:
        entry_path = key.path(self._root)
        meta, reused = self._ensure_entry(
            entry_path,
            route_signature,
            settings,
            reader_factory,
            invariant_values=invariant_values,
        )
        table, total_rows, applied_offset, applied_limit = self._read_slice(entry_path, meta, offset, limit)
        return CacheReadResult(
            table=table,
            total_rows=total_rows,
            applied_offset=applied_offset,
            applied_limit=applied_limit,
            from_cache=reused,
            meta=meta,
        )

    def try_read(
        self,
        key: CacheKey,
        *,
        route_signature: str,
        settings: CacheSettings,
        offset: int,
        limit: int | None,
        invariant_filters: Sequence[InvariantFilterSetting],
        requested_invariants: Mapping[str, Sequence[object]],
    ) -> CacheReadResult | None:
        entry_path = key.path(self._root)
        meta = self._load_meta(entry_path)
        if not _is_meta_valid(meta, route_signature, settings):
            return None
        return self._read_with_invariants(
            entry_path,
            meta,
            offset,
            limit,
            invariant_filters=invariant_filters,
            requested_invariants=requested_invariants,
        )

    def _ensure_entry(
        self,
        entry_path: Path,
        route_signature: str,
        settings: CacheSettings,
        reader_factory: RecordBatchFactory,
        *,
        invariant_values: Mapping[str, Sequence[object]] | None,
    ) -> tuple[dict[str, object], bool]:
        meta = self._load_meta(entry_path)
        if _is_meta_valid(meta, route_signature, settings):
            return meta, True
        self._rebuild_entry(
            entry_path,
            reader_factory,
            settings,
            route_signature,
            requested_invariants=invariant_values,
        )
        fresh = self._load_meta(entry_path)
        if not fresh:
            raise RuntimeError("cache population failed")
        return fresh, False

    def _rebuild_entry(
        self,
        entry_path: Path,
        reader_factory: RecordBatchFactory,
        settings: CacheSettings,
        route_signature: str,
        *,
        requested_invariants: Mapping[str, Sequence[object]] | None,
    ) -> None:
        if entry_path.exists():
            shutil.rmtree(entry_path)
        entry_path.mkdir(parents=True, exist_ok=True)

        reader, closer = reader_factory()
        try:
            schema = reader.schema
            page_rows = max(1, settings.rows_per_page)
            total_rows = 0
            page_index = 0
            current_batches: list[pa.RecordBatch] = []
            current_rows = 0
            pages_written = 0
            invariant_index: dict[str, dict[str, dict[str, object]]] = {}
            while True:
                try:
                    batch = reader.read_next_batch()
                except StopIteration:
                    break
                if batch is None or batch.num_rows == 0:
                    continue
                total_rows += batch.num_rows
                offset = 0
                while offset < batch.num_rows:
                    space = page_rows - current_rows
                    take = min(space, batch.num_rows - offset)
                    if take <= 0:
                        break
                    current_batches.append(batch.slice(offset, take))
                    current_rows += take
                    offset += take
                    if current_rows == page_rows:
                        page_table = pa.Table.from_batches(list(current_batches), schema=schema)
                        self._write_page(entry_path, page_index, current_batches, schema)
                        _update_invariant_index(
                            page_table,
                            page_index,
                            settings.invariant_filters,
                            invariant_index,
                        )
                        pages_written += 1
                        page_index += 1
                        current_batches = []
                        current_rows = 0
            if current_rows > 0:
                page_table = pa.Table.from_batches(list(current_batches), schema=schema)
                self._write_page(entry_path, page_index, current_batches, schema)
                _update_invariant_index(
                    page_table,
                    page_index,
                    settings.invariant_filters,
                    invariant_index,
                )
                pages_written += 1
            invariant_values_meta: dict[str, list[str]] = {}
            for param, entries in invariant_index.items():
                if not isinstance(entries, Mapping):
                    continue
                tokens = sorted(
                    str(token)
                    for token, info in entries.items()
                    if isinstance(info, Mapping)
                    and int(info.get("rows", 0)) > 0
                )
                if tokens:
                    invariant_values_meta[param] = tokens

            meta = {
                "version": 1,
                "created_at": time.time(),
                "expires_at": time.time() + settings.ttl_seconds,
                "total_rows": total_rows,
                "page_rows": page_rows,
                "page_count": pages_written if total_rows else 0,
                "route_signature": route_signature,
                "schema": base64.b64encode(schema.serialize().to_pybytes()).decode("ascii"),
                "order_by": list(settings.order_by),
                "invariant_values": invariant_values_meta
                if invariant_values_meta
                else canonicalize_invariant_mapping(
                    requested_invariants,
                    settings.invariant_filters,
                ),
                "invariant_index": invariant_index,
            }
            self._write_meta(entry_path, meta)
        finally:
            closer()

    def _write_page(
        self,
        entry_path: Path,
        page_index: int,
        batches: Sequence[pa.RecordBatch],
        schema: pa.Schema,
    ) -> None:
        if not batches:
            return
        table = pa.Table.from_batches(list(batches), schema=schema)
        if table.num_rows == 0:
            return
        target = entry_path / f"page-{page_index:05d}.parquet"
        pq.write_table(table, target)

    def _read_slice(
        self,
        entry_path: Path,
        meta: Mapping[str, object],
        offset: int,
        limit: int | None,
    ) -> tuple[pa.Table, int, int, int | None]:
        total_rows = int(meta.get("total_rows", 0))
        page_rows = max(1, int(meta.get("page_rows", 1)))
        schema = _schema_from_meta(meta)
        if total_rows == 0:
            empty = pa.Table.from_batches([], schema=schema)
            applied_offset = 0
            applied_limit = 0 if limit is not None else None
            return empty, 0, applied_offset, applied_limit
        applied_offset = min(max(offset, 0), total_rows)
        requested_limit = None if limit is None else max(0, int(limit))
        if applied_offset >= total_rows:
            empty = pa.Table.from_batches([], schema=schema)
            applied_limit = 0 if requested_limit is not None else None
            return empty, total_rows, total_rows, applied_limit
        remaining = total_rows - applied_offset if requested_limit is None else requested_limit
        slices: list[pa.Table] = []
        cursor = applied_offset
        while remaining > 0 and cursor < total_rows:
            page_index = cursor // page_rows
            page_path = entry_path / f"page-{page_index:05d}.parquet"
            if not page_path.exists():
                break
            page_table = pq.read_table(page_path)
            start_in_page = cursor - page_index * page_rows
            available = max(0, page_table.num_rows - start_in_page)
            if available == 0:
                break
            take = available if requested_limit is None else min(available, remaining)
            slices.append(page_table.slice(start_in_page, take))
            cursor += take
            if requested_limit is None:
                remaining = total_rows - cursor
            else:
                remaining -= take
        if not slices:
            empty = pa.Table.from_batches([], schema=schema)
            applied_limit = 0 if requested_limit is not None else None
            return empty, total_rows, applied_offset, applied_limit
        table = pa.concat_tables(slices) if len(slices) > 1 else slices[0]
        applied_limit = None if requested_limit is None else min(requested_limit, max(0, total_rows - applied_offset))
        return table, total_rows, applied_offset, applied_limit

    def _read_with_invariants(
        self,
        entry_path: Path,
        meta: Mapping[str, object],
        offset: int,
        limit: int | None,
        *,
        invariant_filters: Sequence[InvariantFilterSetting],
        requested_invariants: Mapping[str, Sequence[object]],
    ) -> CacheReadResult | None:
        meta_values = _meta_invariant_sets(meta)
        if not requested_invariants:
            table, total_rows, applied_offset, applied_limit = self._read_slice(entry_path, meta, offset, limit)
            return CacheReadResult(
                table=table,
                total_rows=total_rows,
                applied_offset=applied_offset,
                applied_limit=applied_limit,
                from_cache=True,
                meta=meta,
            )

        filters_to_apply: dict[str, Sequence[object]] = {}
        schema = _schema_from_meta(meta)
        column_types = {field.name: field.type for field in schema}
        for setting in invariant_filters:
            values = requested_invariants.get(setting.param)
            if not values:
                continue
            column_type = column_types.get(setting.column)
            normalized_for_tokens: list[object]
            if column_type is not None:
                normalized_for_tokens = []
                for value in values:
                    converted = _coerce_invariant_value_for_column(value, column_type)
                    if converted is _INVALID_INVARIANT_VALUE:
                        normalized_for_tokens.append(value)
                    else:
                        normalized_for_tokens.append(converted)
            else:
                normalized_for_tokens = list(values)
            requested_tokens = {
                canonicalize_invariant_value(value, setting)
                for value in normalized_for_tokens
            }
            meta_tokens = meta_values.get(setting.param)
            if meta_tokens is None:
                filters_to_apply[setting.param] = tuple(normalized_for_tokens)
                continue
            if not requested_tokens.issubset(meta_tokens):
                return None
            if requested_tokens != meta_tokens:
                filters_to_apply[setting.param] = tuple(normalized_for_tokens)

        if not filters_to_apply:
            table, total_rows, applied_offset, applied_limit = self._read_slice(entry_path, meta, offset, limit)
            return CacheReadResult(
                table=table,
                total_rows=total_rows,
                applied_offset=applied_offset,
                applied_limit=applied_limit,
                from_cache=True,
                meta=meta,
            )

        filtered = self._read_filtered_slice(
            entry_path,
            meta,
            offset,
            limit,
            invariant_filters=invariant_filters,
            filter_values=filters_to_apply,
        )
        return filtered

    def _read_filtered_slice(
        self,
        entry_path: Path,
        meta: Mapping[str, object],
        offset: int,
        limit: int | None,
        *,
        invariant_filters: Sequence[InvariantFilterSetting],
        filter_values: Mapping[str, Sequence[object]],
    ) -> CacheReadResult | None:
        if not filter_values:
            return None
        schema = _schema_from_meta(meta)
        total_rows = int(meta.get("total_rows", 0))
        if total_rows == 0:
            empty = pa.Table.from_batches([], schema=schema)
            applied_offset = 0
            applied_limit = 0 if limit is not None else None
            return CacheReadResult(
                table=empty,
                total_rows=0,
                applied_offset=applied_offset,
                applied_limit=applied_limit,
                from_cache=True,
                meta=meta,
            )

        relevant_filters = [f for f in invariant_filters if f.param in filter_values]
        if not relevant_filters:
            return None

        page_indices = _select_pages_for_invariants(meta, relevant_filters, filter_values)
        if page_indices is None:
            page_indices = list(range(int(meta.get("page_count", 0))))
        if not page_indices:
            empty = pa.Table.from_batches([], schema=schema)
            applied_offset = 0 if offset <= 0 else 0
            applied_limit = 0 if limit is not None else None
            return CacheReadResult(
                table=empty,
                total_rows=0,
                applied_offset=0,
                applied_limit=applied_limit,
                from_cache=True,
                meta=meta,
            )

        filtered_tables: list[pa.Table] = []
        total_filtered_rows = 0
        skip = max(0, offset)
        collected = 0
        target = None if limit is None else max(0, limit)

        for page_index in page_indices:
            page_path = entry_path / f"page-{page_index:05d}.parquet"
            if not page_path.exists():
                continue
            page_table = pq.read_table(page_path)
            filtered_table = _apply_invariant_filters(page_table, relevant_filters, filter_values)
            rows = filtered_table.num_rows
            if rows == 0:
                continue
            total_filtered_rows += rows
            if skip >= rows:
                skip -= rows
                continue
            start = skip
            skip = 0
            if target is None:
                filtered_tables.append(filtered_table.slice(start))
            else:
                take = min(target - collected, rows - start)
                if take > 0:
                    filtered_tables.append(filtered_table.slice(start, take))
                    collected += take
                    if collected >= target:
                        # continue scanning for accurate counts
                        continue

        if filtered_tables:
            table = (
                pa.concat_tables(filtered_tables)
                if len(filtered_tables) > 1
                else filtered_tables[0]
            )
        else:
            table = pa.Table.from_batches([], schema=schema)

        applied_offset = min(max(offset, 0), total_filtered_rows)
        applied_limit = None if limit is None else min(limit, max(0, total_filtered_rows - applied_offset))
        return CacheReadResult(
            table=table,
            total_rows=total_filtered_rows,
            applied_offset=applied_offset,
            applied_limit=applied_limit,
            from_cache=True,
            meta=meta,
        )

    def _load_meta(self, entry_path: Path) -> dict[str, object] | None:
        meta_path = entry_path / "meta.json"
        if not meta_path.exists():
            return None
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def _write_meta(self, entry_path: Path, meta: Mapping[str, object]) -> None:
        meta_path = entry_path / "meta.json"
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")


def _parse_order_by(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = [segment.strip() for segment in raw.split(",")]
        return [part for part in parts if part]
    if isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray)):
        order: list[str] = []
        for item in raw:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                order.append(text)
        return order
    raise RuntimeError("cache.order_by must be a string or list of column names")


def parse_invariant_filters(raw: object) -> list[InvariantFilterSetting]:
    filters: list[InvariantFilterSetting] = []
    known_keys = {"param", "name", "column", "field", "separator", "case_insensitive"}

    def extra_from_mapping(data: Mapping[str, object]) -> dict[str, object]:
        extras: dict[str, object] = {}
        for key, value in data.items():
            key_text = key if isinstance(key, str) else str(key)
            if key_text in known_keys:
                continue
            extras[key_text] = value
        return extras

    if isinstance(raw, Mapping):
        for key, value in raw.items():
            if isinstance(value, Mapping):
                mapping = {key if isinstance(key, str) else str(key): val for key, val in value.items()}
                param = str(mapping.get("param", key))
                column = str(mapping.get("column", param))
                separator_raw = mapping.get("separator")
                separator = str(separator_raw) if separator_raw is not None else None
                case_insensitive = bool(mapping.get("case_insensitive", False))
                extra = extra_from_mapping(mapping)
                filters.append(
                    InvariantFilterSetting(
                        param=param,
                        column=column,
                        separator=separator,
                        case_insensitive=case_insensitive,
                        extra=extra,
                    )
                )
            else:
                param = str(key)
                column = str(value)
                filters.append(InvariantFilterSetting(param=param, column=column))
        return filters
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        for item in raw:
            if isinstance(item, Mapping):
                mapping = {key if isinstance(key, str) else str(key): val for key, val in item.items()}
                raw_param = (
                    mapping.get("param")
                    or mapping.get("name")
                    or mapping.get("column")
                    or mapping.get("field")
                )
                if raw_param is None:
                    continue
                param = str(raw_param)
                column = str(mapping.get("column", param))
                separator_raw = mapping.get("separator")
                separator = str(separator_raw) if separator_raw is not None else None
                case_insensitive = bool(mapping.get("case_insensitive", False))
                extra = extra_from_mapping(mapping)
                filters.append(
                    InvariantFilterSetting(
                        param=param,
                        column=column,
                        separator=separator,
                        case_insensitive=case_insensitive,
                        extra=extra,
                    )
                )
            elif item is not None:
                param = str(item)
                filters.append(InvariantFilterSetting(param=param, column=param))
    return filters


def _collect_invariant_requests(
    filters: Sequence[InvariantFilterSetting],
    params: Mapping[str, object],
) -> dict[str, tuple[object, ...]]:
    collected: dict[str, tuple[object, ...]] = {}
    for setting in filters:
        raw_value = params.get(setting.param)
        normalized = normalize_invariant_value(raw_value, setting)
        if normalized:
            collected[setting.param] = tuple(normalized)
    return collected


def _sorted_invariant_filters(
    filters: Sequence[InvariantFilterSetting],
) -> tuple[InvariantFilterSetting, ...]:
    if not filters:
        return ()
    return tuple(
        sorted(
            filters,
            key=lambda setting: (
                setting.param,
                setting.column,
                setting.separator or "",
                setting.case_insensitive,
            ),
        )
    )


def _string_represents_null(value: str) -> bool:
    return value.strip().lower() == "__null__"


def normalize_invariant_value(
    value: object,
    setting: InvariantFilterSetting,
) -> list[object]:
    if value is None:
        return []
    if isinstance(value, str):
        if value == "":
            return []
        if _string_represents_null(value):
            return [None]
        if setting.separator:
            normalized: list[object] = []
            for part in value.split(setting.separator):
                trimmed = part.strip()
                if not trimmed:
                    continue
                if _string_represents_null(trimmed):
                    normalized.append(None)
                else:
                    normalized.append(trimmed)
            return normalized
        return [value]
    if isinstance(value, (bytes, bytearray)):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        flattened: list[object] = []
        for item in value:
            flattened.extend(normalize_invariant_value(item, setting))
        return flattened
    return [value]


def canonicalize_invariant_mapping(
    requested: Mapping[str, Sequence[object]] | None,
    filters: Sequence[InvariantFilterSetting],
) -> dict[str, list[str]]:
    if not requested:
        return {}
    by_param = {setting.param: setting for setting in filters}
    canonical: dict[str, list[str]] = {}
    for param, values in requested.items():
        setting = by_param.get(param)
        if setting is None:
            continue
        tokens = {
            canonicalize_invariant_value(value, setting)
            for value in values
        }
        if tokens:
            canonical[param] = sorted(tokens)
    return canonical


def _canonicalize_numeric_token(value: int | float | decimal.Decimal) -> str:
    if isinstance(value, decimal.Decimal):
        if not value.is_finite():
            return "str:" + str(value)
        numeric = value
    elif isinstance(value, float):
        if not math.isfinite(value):
            return "num:" + str(value)
        numeric = decimal.Decimal(str(value))
    else:
        numeric = decimal.Decimal(value)

    normalized = numeric.normalize()
    if normalized == 0:
        normalized = decimal.Decimal(0)
    token = format(normalized, "f")
    if "." in token:
        token = token.rstrip("0").rstrip(".")
    if not token:
        token = "0"
    return "num:" + token


def _normalize_casefold_text(value: str, *, case_insensitive: bool) -> str:
    """Return ``value`` lower-cased when ``case_insensitive`` is enabled."""

    return value.lower() if case_insensitive else value


_INVALID_INVARIANT_VALUE = object()


def _coerce_invariant_value_for_column(
    value: object, column_type: pa.DataType
) -> object:
    """Attempt to coerce ``value`` to the Arrow column's logical type."""

    try:
        if pa.types.is_integer(column_type):
            return _coerce_integer_like(value)
        if pa.types.is_floating(column_type):
            return _coerce_float_like(value)
        if pa.types.is_decimal(column_type):
            return _coerce_decimal_like(value)
    except (TypeError, ValueError, decimal.InvalidOperation):
        return _INVALID_INVARIANT_VALUE
    return value


def _coerce_integer_like(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, decimal.Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise ValueError("decimal value is not an integer")
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError("float value is not an integer")
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("empty string")
        return int(text, 10)
    return int(value)  # type: ignore[arg-type]


def _coerce_float_like(value: object) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float")
        return value
    if isinstance(value, decimal.Decimal):
        if not value.is_finite():
            raise ValueError("non-finite decimal")
        return float(value)
    if isinstance(value, int):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("empty string")
        result = float(text)
        if not math.isfinite(result):
            raise ValueError("non-finite float")
        return result
    result = float(value)  # type: ignore[arg-type]
    if not math.isfinite(result):
        raise ValueError("non-finite float")
    return result


def _coerce_decimal_like(value: object) -> decimal.Decimal:
    if isinstance(value, decimal.Decimal):
        decimal_value = value
    elif isinstance(value, bool):
        decimal_value = decimal.Decimal(int(value))
    elif isinstance(value, (int, float)):
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("non-finite float")
            decimal_value = decimal.Decimal(str(value))
        else:
            decimal_value = decimal.Decimal(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("empty string")
        decimal_value = decimal.Decimal(text)
    else:
        decimal_value = decimal.Decimal(value)  # type: ignore[arg-type]
    if not decimal_value.is_finite():
        raise ValueError("non-finite decimal")
    return decimal_value


def _prepare_invariant_filter_values(
    values: Sequence[object],
    column: pa.ChunkedArray,
    setting: InvariantFilterSetting,
) -> tuple[list[object], bool, bool]:
    """Normalise requested values for invariant filtering.

    Returns ``(normalised_values, include_null, use_casefold)`` where ``use_casefold``
    indicates the column should be lower-cased to match the values.
    """

    include_null = any(value is None for value in values)
    non_null = [value for value in values if value is not None]
    column_type = column.type

    coerced: list[object] = []
    for item in non_null:
        converted = _coerce_invariant_value_for_column(item, column_type)
        if converted is _INVALID_INVARIANT_VALUE:
            continue
        coerced.append(converted)

    use_casefold = setting.case_insensitive and (
        pa.types.is_string(column_type)
        or pa.types.is_large_string(column_type)
    )
    if use_casefold:
        normalised = [
            _normalize_casefold_text(str(item), case_insensitive=True)
            for item in coerced
        ]
    else:
        normalised = coerced
    return normalised, include_null, use_casefold


def canonicalize_invariant_value(value: object, setting: InvariantFilterSetting) -> str:
    if value is None:
        token = "__null__"
    elif isinstance(value, bool):
        token = f"bool:{str(value).lower()}"
    elif isinstance(value, (int, float, decimal.Decimal)):
        token = _canonicalize_numeric_token(value)
    elif isinstance(value, (bytes, bytearray)):
        token = "bytes:" + base64.b64encode(bytes(value)).decode("ascii")
    elif hasattr(value, "isoformat"):
        try:
            token = "datetime:" + value.isoformat()
        except Exception:
            token = "str:" + str(value)
    else:
        token = "str:" + str(value)
    if setting.case_insensitive and token.startswith("str:"):
        token = "str:" + _normalize_casefold_text(token[4:], case_insensitive=True)
    return token


def _meta_invariant_sets(meta: Mapping[str, object]) -> dict[str, set[str]]:
    raw = meta.get("invariant_values")
    if not isinstance(raw, Mapping):
        return {}
    values: dict[str, set[str]] = {}
    for key, items in raw.items():
        if isinstance(items, Sequence) and not isinstance(items, (str, bytes, bytearray)):
            values[str(key)] = {str(item) for item in items}
    return values


def _select_pages_for_invariants(
    meta: Mapping[str, object],
    filters: Sequence[InvariantFilterSetting],
    requested: Mapping[str, Sequence[object]],
) -> list[int] | None:
    meta_index = meta.get("invariant_index")
    if not isinstance(meta_index, Mapping):
        return None
    pages: set[int] | None = None
    for setting in filters:
        values = requested.get(setting.param)
        if not values:
            continue
        param_index = meta_index.get(setting.param)
        if not isinstance(param_index, Mapping):
            return None
        value_pages: set[int] = set()
        for value in values:
            token = canonicalize_invariant_value(value, setting)
            entry = param_index.get(token)
            if not isinstance(entry, Mapping):
                return []
            page_list = entry.get("pages", [])
            if isinstance(page_list, Sequence):
                for page in page_list:
                    try:
                        value_pages.add(int(page))
                    except (TypeError, ValueError):
                        continue
        if pages is None:
            pages = value_pages
        else:
            pages &= value_pages
        if not pages:
            return []
    if pages is None:
        return None
    return sorted(pages)


def _apply_invariant_filters(
    table: pa.Table,
    filters: Sequence[InvariantFilterSetting],
    requested: Mapping[str, Sequence[object]],
) -> pa.Table:
    result = table
    for setting in filters:
        values = requested.get(setting.param)
        if not values:
            continue
        if setting.column not in result.column_names:
            continue
        column = result.column(setting.column)
        normalized_values, include_null, use_casefold = _prepare_invariant_filter_values(
            values,
            column,
            setting,
        )
        if not normalized_values and not include_null:
            return pa.Table.from_batches([], schema=result.schema)
        column_data = pc.utf8_lower(column) if use_casefold else column
        value_set = pa.array(normalized_values) if normalized_values else None
        mask = None
        if value_set is not None and len(value_set) > 0:
            mask = pc.is_in(column_data, value_set=value_set)
        if include_null:
            null_mask = pc.is_null(column)
            mask = null_mask if mask is None else pc.or_(mask, null_mask)
        if mask is None:
            return pa.Table.from_batches([], schema=result.schema)
        result = result.filter(mask)
        if result.num_rows == 0:
            return result
    return result


def _update_invariant_index(
    table: pa.Table,
    page_index: int,
    filters: Sequence[InvariantFilterSetting],
    index: dict[str, dict[str, dict[str, object]]],
) -> None:
    for setting in filters:
        if setting.column not in table.column_names:
            continue
        column = table.column(setting.column)
        counts = pc.value_counts(column)
        if counts is None:
            continue
        param_entry = index.setdefault(setting.param, {})
        for item in counts.to_pylist():
            value = item.get("values")
            count = int(item.get("counts", 0))
            token = canonicalize_invariant_value(value, setting)
            display = "" if value is None else str(value)
            entry = param_entry.setdefault(
                token,
                {
                    "pages": [],
                    "rows": 0,
                    "sample": display,
                },
            )
            pages = entry.setdefault("pages", [])
            if page_index not in pages:
                pages.append(page_index)
            entry["rows"] = int(entry.get("rows", 0)) + count
            if "sample" not in entry and display:
                entry["sample"] = display


def _is_meta_valid(
    meta: Mapping[str, object] | None,
    route_signature: str,
    settings: CacheSettings,
) -> bool:
    if not isinstance(meta, Mapping):
        return False
    if meta.get("route_signature") != route_signature:
        return False
    try:
        page_rows = int(meta.get("page_rows", settings.rows_per_page))
    except (TypeError, ValueError):
        return False
    if page_rows != settings.rows_per_page:
        return False
    stored_order = meta.get("order_by")
    normalized_order = (
        [str(item) for item in stored_order]
        if isinstance(stored_order, Sequence) and not isinstance(stored_order, (str, bytes, bytearray))
        else []
    )
    if list(settings.order_by) != normalized_order:
        return False
    try:
        expires = float(meta.get("expires_at", 0))
    except (TypeError, ValueError):
        return False
    return expires > time.time()


def resolve_cache_settings(route: RouteDefinition, config: CacheConfig) -> CacheSettings:
    metadata = route.metadata if isinstance(route.metadata, Mapping) else {}
    cache_meta = metadata.get("cache") if isinstance(metadata, Mapping) else None
    enabled = config.enabled
    ttl_seconds = max(0, int(config.ttl_seconds))
    rows_per_page = max(0, int(config.page_rows))
    enforce_page_size = bool(config.enforce_global_page_size)
    invariant_filters: list[InvariantFilterSetting] = []
    order_by: tuple[str, ...] = ()
    if isinstance(cache_meta, Mapping):
        if "enabled" in cache_meta:
            enabled = bool(cache_meta["enabled"])
        if "ttl_seconds" in cache_meta:
            ttl_seconds = max(0, int(cache_meta["ttl_seconds"]))
        if "ttl_hours" in cache_meta:
            ttl_seconds = max(0, int(float(cache_meta["ttl_hours"]) * 3600))
        if "rows_per_page" in cache_meta:
            rows_per_page = max(0, int(cache_meta["rows_per_page"]))
        if "page_rows" in cache_meta:
            rows_per_page = max(0, int(cache_meta["page_rows"]))
        if "enforce_page_size" in cache_meta:
            enforce_page_size = bool(cache_meta["enforce_page_size"])
        elif "rows_per_page" in cache_meta or "page_rows" in cache_meta:
            enforce_page_size = True
        invariants_meta = cache_meta.get("invariant_filters")
        if invariants_meta is not None:
            invariant_filters = parse_invariant_filters(invariants_meta)
        raw_order = cache_meta.get("order_by")
        if raw_order is None and "order-by" in cache_meta:
            raw_order = cache_meta["order-by"]
        if raw_order is not None:
            order_values = _parse_order_by(raw_order)
            if not order_values:
                raise RuntimeError(f"cache.order_by must list at least one column for route '{route.id}'")
            order_by = tuple(order_values)
    if rows_per_page <= 0:
        enabled = False
    route_cache_mode = getattr(route, "cache_mode", "materialize")
    if isinstance(route_cache_mode, str) and route_cache_mode.lower() != "materialize":
        enabled = False
    if enabled and rows_per_page > 0 and not order_by:
        raise RuntimeError(f"cache.order_by must list at least one column for route '{route.id}'")
    return CacheSettings(
        enabled=enabled,
        ttl_seconds=ttl_seconds,
        rows_per_page=rows_per_page if rows_per_page > 0 else 0,
        enforce_page_size=enforce_page_size,
        invariant_filters=tuple(invariant_filters),
        order_by=order_by,
    )


def fetch_cached_table(
    route: RouteDefinition,
    params: Mapping[str, object],
    ordered_params: Sequence[object],
    *,
    offset: int,
    limit: int | None,
    store: CacheStore | None,
    config: CacheConfig,
    reader_factory: RecordBatchFactory | None = None,
    execute_sql: Callable[[], pa.Table] | None = None,
) -> CacheQueryResult:
    settings = resolve_cache_settings(route, config)
    effective_offset, effective_limit = _effective_window(offset, limit, settings)
    invariant_requests = _collect_invariant_requests(settings.invariant_filters, params)
    reader_factory_fn = reader_factory or (lambda: _record_batch_reader(route.prepared_sql, ordered_params))
    execute_sql_fn = execute_sql or (lambda: _execute_sql(route.prepared_sql, ordered_params))

    if not store or not settings.enabled:
        table = execute_sql_fn()
        table = _sort_table(table, settings.order_by)
        sliced, total_rows, applied_offset, applied_limit = _slice_table(
            table, effective_offset, effective_limit
        )
        return CacheQueryResult(
            table=sliced,
            total_rows=total_rows,
            applied_offset=applied_offset,
            applied_limit=applied_limit,
            used_cache=False,
            cache_hit=False,
            meta=None,
        )
    route_signature = _route_signature(route)
    cache_params = _prepare_cache_params(params, settings.invariant_filters)

    if settings.invariant_filters:
        reuse = _reuse_invariant_caches(
            route,
            params,
            cache_params,
            store,
            settings,
            route_signature,
            effective_offset,
            effective_limit,
            limit,
            invariant_requests,
            settings.order_by,
        )
        if reuse is not None:
            return _sorted_query_result(reuse, settings.order_by)

    key = store.compute_key(route, cache_params, settings)
    read = store.try_read(
        key,
        route_signature=route_signature,
        settings=settings,
        offset=effective_offset,
        limit=effective_limit,
        invariant_filters=settings.invariant_filters,
        requested_invariants=invariant_requests,
    )
    cache_hit = True
    if read is None:
        read = store.get_or_populate(
            key,
            route_signature=route_signature,
            settings=settings,
            offset=effective_offset,
            limit=effective_limit,
            reader_factory=reader_factory_fn,
            invariant_values=invariant_requests,
        )
        cache_hit = read.from_cache
        if invariant_requests:
            reread = store.try_read(
                key,
                route_signature=route_signature,
                settings=settings,
                offset=effective_offset,
                limit=effective_limit,
                invariant_filters=settings.invariant_filters,
                requested_invariants=invariant_requests,
            )
            if reread is not None:
                read = reread

    applied_limit = _finalize_limit(
        read.applied_limit,
        read.total_rows,
        read.applied_offset,
        limit,
        settings,
    )
    return _sorted_query_result(
        CacheQueryResult(
            table=read.table,
            total_rows=read.total_rows,
            applied_offset=read.applied_offset,
            applied_limit=applied_limit,
            used_cache=True,
            cache_hit=cache_hit,
            meta=read.meta,
        ),
        settings.order_by,
    )


def materialize_parquet_artifacts(
    route: RouteDefinition,
    params: Mapping[str, object],
    ordered_params: Sequence[object],
    *,
    store: CacheStore | None,
    config: CacheConfig,
    reader_factory: RecordBatchFactory | None = None,
) -> CacheArtifactResult:
    settings = resolve_cache_settings(route, config)
    if not store or not settings.enabled:
        raise RuntimeError(
            f"Route '{route.id}' does not support parquet_path dependencies because caching is disabled"
        )
    if settings.invariant_filters:
        raise RuntimeError(
            f"Route '{route.id}' cannot be used in parquet_path mode while invariant filters are configured"
        )
    requests = _collect_invariant_requests(settings.invariant_filters, params)
    if requests:
        raise RuntimeError(
            f"Route '{route.id}' received invariant-filter overrides incompatible with parquet_path mode"
        )
    reader_factory_fn = reader_factory or (lambda: _record_batch_reader(route.prepared_sql, ordered_params))
    cache_params = _prepare_cache_params(params, settings.invariant_filters)
    key = store.compute_key(route, cache_params, settings)
    route_signature = _route_signature(route)
    store.get_or_populate(
        key,
        route_signature=route_signature,
        settings=settings,
        offset=0,
        limit=None,
        reader_factory=reader_factory_fn,
        invariant_values=None,
    )
    entry_path = key.path(store._root)
    meta = store._load_meta(entry_path)
    if not meta:
        raise RuntimeError(f"Failed to materialize parquet artifacts for route '{route.id}'")
    schema = _schema_from_meta(meta)
    total_rows = int(meta.get("total_rows", 0))
    paths = tuple(sorted(entry_path.glob("page-*.parquet")))
    return CacheArtifactResult(paths=paths, schema=schema, total_rows=total_rows, cache_key=key)


def _reuse_invariant_caches(
    route: RouteDefinition,
    params: Mapping[str, object],
    cache_params: Mapping[str, object],
    store: CacheStore,
    settings: CacheSettings,
    route_signature: str,
    offset: int,
    limit: int | None,
    client_limit: int | None,
    requested_invariants: Mapping[str, Sequence[object]],
    order_by: Sequence[str],
) -> CacheQueryResult | None:
    if not requested_invariants:
        return None

    original_params = dict(params)
    exact_key = store.compute_key(route, cache_params, settings)
    exact_hit = store.try_read(
        exact_key,
        route_signature=route_signature,
        settings=settings,
        offset=offset,
        limit=limit,
        invariant_filters=settings.invariant_filters,
        requested_invariants=requested_invariants,
    )
    if exact_hit is not None:
        applied_limit = _finalize_limit(
            exact_hit.applied_limit,
            exact_hit.total_rows,
            exact_hit.applied_offset,
            client_limit,
            settings,
        )
        return CacheQueryResult(
            table=exact_hit.table,
            total_rows=exact_hit.total_rows,
            applied_offset=exact_hit.applied_offset,
            applied_limit=applied_limit,
            used_cache=True,
            cache_hit=True,
            meta=exact_hit.meta,
        )

    base_params = _drop_invariant_params(dict(cache_params), settings.invariant_filters)
    if base_params != dict(cache_params):
        base_key = store.compute_key(route, base_params, settings)
        superset_hit = store.try_read(
            base_key,
            route_signature=route_signature,
            settings=settings,
            offset=offset,
            limit=limit,
            invariant_filters=settings.invariant_filters,
            requested_invariants=requested_invariants,
        )
        if superset_hit is not None:
            applied_limit = _finalize_limit(
                superset_hit.applied_limit,
                superset_hit.total_rows,
                superset_hit.applied_offset,
                client_limit,
                settings,
            )
            return CacheQueryResult(
                table=superset_hit.table,
                total_rows=superset_hit.total_rows,
                applied_offset=superset_hit.applied_offset,
                applied_limit=applied_limit,
                used_cache=True,
                cache_hit=True,
                meta=superset_hit.meta,
            )

    combinations = _generate_invariant_combinations(settings.invariant_filters, requested_invariants)
    if not combinations:
        return None

    tables: list[pa.Table] = []
    for combo in combinations:
        combo_params = dict(original_params)
        combo_requests: dict[str, tuple[object, ...]] = {}
        for param, value in combo.items():
            combo_params[param] = value
            combo_requests[param] = (value,)
        combo_cache_params = _prepare_cache_params(combo_params, settings.invariant_filters)
        combo_key = store.compute_key(route, combo_cache_params, settings)
        combo_hit = store.try_read(
            combo_key,
            route_signature=route_signature,
            settings=settings,
            offset=0,
            limit=None,
            invariant_filters=settings.invariant_filters,
            requested_invariants=combo_requests,
        )
        if combo_hit is None:
            return None
        tables.append(combo_hit.table)

    combined_table, total_rows, applied_offset, raw_limit = _combine_tables(
        tables,
        offset,
        limit,
        order_by,
    )
    applied_limit = _finalize_limit(
        raw_limit,
        total_rows,
        applied_offset,
        client_limit,
        settings,
    )
    return CacheQueryResult(
        table=combined_table,
        total_rows=total_rows,
        applied_offset=applied_offset,
        applied_limit=applied_limit,
        used_cache=True,
        cache_hit=True,
        meta=None,
    )


def _prepare_cache_params(
    params: Mapping[str, object],
    filters: Sequence[InvariantFilterSetting],
) -> dict[str, object]:
    canonical = dict(params)
    for setting in filters:
        value = canonical.get(setting.param)
        if value is None:
            canonical.pop(setting.param, None)
    return canonical


def _drop_invariant_params(
    params: Mapping[str, object],
    filters: Sequence[InvariantFilterSetting],
) -> dict[str, object]:
    cleaned = dict(params)
    for setting in filters:
        cleaned.pop(setting.param, None)
    return cleaned


def _generate_invariant_combinations(
    filters: Sequence[InvariantFilterSetting],
    requested: Mapping[str, Sequence[object]],
) -> list[dict[str, object]]:
    ordered_params: list[str] = []
    value_lists: list[Sequence[object]] = []
    for setting in filters:
        values = requested.get(setting.param)
        if not values:
            continue
        ordered_params.append(setting.param)
        value_lists.append(values)
    if not ordered_params:
        return []
    combinations: list[dict[str, object]] = []
    for combo in product(*value_lists):
        combination: dict[str, object] = {}
        for param, value in zip(ordered_params, combo):
            combination[param] = value
        combinations.append(combination)
    return combinations


def _combine_tables(
    tables: Sequence[pa.Table],
    offset: int,
    limit: int | None,
    order_by: Sequence[str],
) -> tuple[pa.Table, int, int, int | None]:
    if not tables:
        empty = pa.Table.from_batches([], schema=pa.schema([]))
        applied_offset = 0 if offset <= 0 else max(0, offset)
        applied_limit = 0 if limit is not None else None
        return empty, 0, applied_offset, applied_limit

    combined = pa.concat_tables(list(tables)) if len(tables) > 1 else tables[0]
    combined = _sort_table(combined, order_by)
    sliced, total_rows, applied_offset, applied_limit = _slice_table(
        combined,
        offset,
        limit,
    )
    return sliced, total_rows, applied_offset, applied_limit


def _sort_table(table: pa.Table, order_by: Sequence[str]) -> pa.Table:
    if not order_by:
        return table
    missing = [column for column in order_by if column not in table.column_names]
    if missing:
        raise RuntimeError(
            f"cache.order_by column '{missing[0]}' is not present in the result set"
        )
    if table.num_rows <= 1:
        return table
    sort_keys = [(column, "ascending") for column in order_by]
    return table.sort_by(sort_keys)


def _sorted_query_result(
    result: CacheQueryResult,
    order_by: Sequence[str],
) -> CacheQueryResult:
    if not order_by:
        return result
    return replace(result, table=_sort_table(result.table, order_by))


def _finalize_limit(
    applied_limit: int | None,
    total_rows: int,
    applied_offset: int,
    client_limit: int | None,
    settings: CacheSettings,
) -> int | None:
    if client_limit is not None and settings.enforce_page_size and settings.rows_per_page > 0:
        return min(settings.rows_per_page, max(0, total_rows - applied_offset))
    if client_limit is not None and applied_limit is None:
        return min(client_limit, max(0, total_rows - applied_offset))
    return applied_limit


def _slice_table(
    table: pa.Table,
    offset: int,
    limit: int | None,
) -> tuple[pa.Table, int, int, int | None]:
    total = table.num_rows
    start = max(0, offset)
    if start >= total:
        empty = table.slice(total, 0)
        return empty, total, total, 0 if limit is not None else None
    if limit is None:
        return table.slice(start, total - start), total, start, None
    length = max(0, min(limit, total - start))
    return table.slice(start, length), total, start, limit


def _record_batch_reader(
    sql: str,
    params: Sequence[object],
) -> tuple[pa.RecordBatchReader, Callable[[], None]]:
    con = duckdb.connect()
    cursor = con.execute(sql, params)
    reader = cursor.fetch_record_batch()
    return reader, con.close


def _execute_sql(sql: str, params: Sequence[object]) -> pa.Table:
    con = duckdb.connect()
    try:
        cursor = con.execute(sql, params)
        return cursor.fetch_arrow_table()
    finally:
        con.close()


def _effective_window(
    offset: int,
    limit: int | None,
    settings: CacheSettings,
) -> tuple[int, int | None]:
    if not settings.enabled or settings.rows_per_page <= 0:
        return max(0, offset), limit if limit is None else max(0, limit)
    if not settings.enforce_page_size or limit is None:
        return max(0, offset), None if limit is None else max(0, limit)
    rows = settings.rows_per_page
    page_index = max(0, offset) // rows
    return page_index * rows, rows


def _route_signature(route: RouteDefinition) -> str:
    payload = {
        "id": route.id,
        "version": route.version,
        "sql": route.prepared_sql,
        "order": list(route.param_order),
    }
    encoded = json.dumps(payload, sort_keys=True, default=_json_default).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _schema_from_meta(meta: Mapping[str, object]) -> pa.Schema:
    raw = meta.get("schema")
    if not raw:
        return pa.schema([])
    data = base64.b64decode(str(raw))
    return paipc.read_schema(pa.BufferReader(data))


def _normalize_mapping(values: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key in sorted(values):
        normalized[str(key)] = values[key]
    return normalized


def _json_default(value: object) -> object:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # pragma: no cover - fallback for unexpected values
            return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    return value


__all__ = [
    "CacheKey",
    "CacheQueryResult",
    "CacheReadResult",
    "CacheSettings",
    "CacheStore",
    "CacheArtifactResult",
    "fetch_cached_table",
    "materialize_parquet_artifacts",
    "resolve_cache_settings",
]
