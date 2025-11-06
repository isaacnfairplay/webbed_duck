"""Utilities for executing compiled routes with dependency resolution."""
from __future__ import annotations

from dataclasses import dataclass
import datetime as _dt
import decimal
import math
import re
from typing import Callable, Mapping, MutableMapping, Sequence

try:  # pragma: no cover - optional dependency for type checking
    from fastapi import Request
except ModuleNotFoundError:  # pragma: no cover - fallback when FastAPI not installed
    Request = object  # type: ignore[misc,assignment]

import duckdb
import pyarrow as pa

from ..config import Config
from ..core.routes import ParameterSpec, RouteDefinition, RouteUse
from ..plugins.loader import PluginLoader
from .cache import (
    CacheQueryResult,
    CacheStore,
    fetch_cached_table,
    materialize_parquet_artifacts,
)
from .preprocess import run_preprocessors


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

_FILE_FUNCTION_NAMES = [
    "read_csv",
    "read_csv_auto",
    "read_parquet",
    "read_json",
    "read_json_auto",
    "read_avro",
    "read_orc",
    "read_ipc",
    "read_arrow",
    "read_feather",
    "read_text",
    "read_excel",
    "read_delta",
    "parquet_scan",
    "csv_scan",
    "json_scan",
    "delta_scan",
    "glob",
    "list_files",
]

_FILE_FUNCTION_PATTERN = re.compile(
    r"\b(?P<func>(" + "|".join(re.escape(name) for name in _FILE_FUNCTION_NAMES) + r"))\s*\((?P<args>[^)]*?)\)",
    re.IGNORECASE,
)


class RouteExecutionError(RuntimeError):
    """Raised when a route or dependency cannot be executed."""


def _filter_literal(value: object, spec: ParameterSpec, route_id: str) -> str:
    if value is None:
        raise RouteExecutionError(
            f"Template parameter '{spec.name}' cannot be null in route '{route_id}'"
        )
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, decimal.Decimal)):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RouteExecutionError(
                f"Template parameter '{spec.name}' must be a finite number in route '{route_id}'"
            )
        return repr(value)
    if isinstance(value, _dt.datetime):
        return f"'{value.isoformat()}'"
    if isinstance(value, _dt.date):
        return f"'{value.isoformat()}'"
    text = str(value)
    escaped = text.replace("'", "''")
    return f"'{escaped}'"


def _filter_identifier(value: object, spec: ParameterSpec, route_id: str) -> str:
    if value is None:
        raise RouteExecutionError(
            f"Template parameter '{spec.name}' cannot be null in route '{route_id}'"
        )
    text = str(value)
    if not _IDENTIFIER_PATTERN.match(text):
        raise RouteExecutionError(
            f"Template parameter '{spec.name}' must be an identifier in route '{route_id}'"
        )
    return text


def _filter_raw(value: object, spec: ParameterSpec, route_id: str) -> str:
    if value is None:
        raise RouteExecutionError(
            f"Template parameter '{spec.name}' cannot be null in route '{route_id}'"
        )
    return str(value)


def _filter_lower(value: object, spec: ParameterSpec, route_id: str) -> str:
    return _filter_raw(value, spec, route_id).lower()


def _filter_upper(value: object, spec: ParameterSpec, route_id: str) -> str:
    return _filter_raw(value, spec, route_id).upper()


_TEMPLATE_FILTERS: Mapping[str, Callable[[object, ParameterSpec, str], str]] = {
    "literal": _filter_literal,
    "identifier": _filter_identifier,
    "raw": _filter_raw,
    "lower": _filter_lower,
    "upper": _filter_upper,
}


def _apply_template_filters(
    value: object, filters: Sequence[str], spec: ParameterSpec, route_id: str
) -> str:
    current: object = value
    for name in filters:
        handler = _TEMPLATE_FILTERS.get(name)
        if handler is None:
            raise RouteExecutionError(
                f"Unsupported template filter '{name}' for parameter '{spec.name}' in route '{route_id}'"
            )
        current = handler(current, spec, route_id)
    return str(current)


def _evaluate_template_guard(spec: ParameterSpec, value: object, route_id: str) -> None:
    guard = spec.guard or {}
    mode_raw = guard.get("mode")
    mode = str(mode_raw).lower() if mode_raw is not None else ""
    if not mode:
        if "pattern" in guard or "regex" in guard:
            mode = "pattern"
        elif "prefix" in guard:
            mode = "prefix"
        elif "choices" in guard:
            mode = "choices"
        elif "identifier" in guard:
            mode = "identifier"
    if not mode:
        return
    text = None if value is None else str(value)
    if mode in {"pattern", "regex"}:
        pattern = guard.get("pattern") or guard.get("regex")
        if not isinstance(pattern, str) or not pattern:
            raise RouteExecutionError(
                f"Guard for parameter '{spec.name}' must define a regex pattern in route '{route_id}'"
            )
        if text is None or not re.fullmatch(pattern, text):
            raise RouteExecutionError(
                f"Parameter '{spec.name}' failed regex guard in route '{route_id}'"
            )
    elif mode == "prefix":
        prefix = guard.get("prefix")
        if not isinstance(prefix, str):
            raise RouteExecutionError(
                f"Guard for parameter '{spec.name}' must define a prefix string in route '{route_id}'"
            )
        if text is None or not text.startswith(prefix):
            raise RouteExecutionError(
                f"Parameter '{spec.name}' must start with '{prefix}' in route '{route_id}'"
            )
    elif mode == "choices":
        choices = guard.get("choices")
        if not isinstance(choices, Sequence) or not choices:
            raise RouteExecutionError(
                f"Guard for parameter '{spec.name}' must define a non-empty choices list in route '{route_id}'"
            )
        normalized = {str(choice) for choice in choices}
        if text is None or text not in normalized:
            raise RouteExecutionError(
                f"Parameter '{spec.name}' must be one of {sorted(normalized)} in route '{route_id}'"
            )
    elif mode == "identifier":
        if text is None or not _IDENTIFIER_PATTERN.match(text):
            raise RouteExecutionError(
                f"Parameter '{spec.name}' must be an identifier in route '{route_id}'"
            )
    else:
        # Unknown guard types are ignored until supported explicitly.
        return
@dataclass(slots=True)
class _PreparedRoute:
    params: Mapping[str, object]
    ordered: Sequence[object]
    bindings: Mapping[str, object]


class RouteExecutor:
    """Execute routes while honoring declarative dependencies."""

    def __init__(
        self,
        routes_by_id: Mapping[str, RouteDefinition],
        *,
        cache_store: CacheStore | None,
        config: Config,
        plugin_loader: PluginLoader,
    ) -> None:
        self._routes = dict(routes_by_id)
        self._cache_store = cache_store
        self._cache_config = config.cache
        self._stack: list[str] = []
        self._plugin_loader = plugin_loader
        self._interpolation_config = config.interpolation

    def execute_relation(
        self,
        route: RouteDefinition,
        params: Mapping[str, object],
        *,
        ordered: Sequence[object] | None = None,
        preprocessed: bool = False,
        offset: int = 0,
        limit: int | None = None,
        request: Request | None = None,
    ) -> CacheQueryResult:
        prepared = self._prepare(
            route,
            params,
            ordered=ordered,
            preprocessed=preprocessed,
            request=request,
        )
        return self._run_relation(route, prepared, offset=offset, limit=limit, request=request)

    def _run_relation(
        self,
        route: RouteDefinition,
        prepared: _PreparedRoute,
        *,
        offset: int,
        limit: int | None,
        request: Request | None,
    ) -> CacheQueryResult:
        if route.id in self._stack:
            raise RouteExecutionError(f"Circular dependency detected while executing route '{route.id}'")
        self._stack.append(route.id)
        try:
            reader_factory = self._make_reader_factory(route, prepared, request=request)
            execute_sql = self._make_execute_fn(route, prepared, request=request)
            return fetch_cached_table(
                route,
                prepared.params,
                prepared.bindings,
                offset=offset,
                limit=limit,
                store=self._cache_store,
                config=self._cache_config,
                reader_factory=reader_factory,
                execute_sql=execute_sql,
            )
        except (duckdb.Error, RuntimeError) as exc:  # pragma: no cover - propagated from cache/duckdb
            raise RouteExecutionError(str(exc)) from exc
        finally:
            self._stack.pop()

    def _prepare(
        self,
        route: RouteDefinition,
        params: Mapping[str, object],
        *,
        ordered: Sequence[object] | None,
        preprocessed: bool,
        request: Request | None = None,
    ) -> _PreparedRoute:
        if preprocessed:
            processed = dict(params)
            ordered_params = list(ordered) if ordered is not None else self._ordered_from_processed(route, processed)
            bindings = self._build_bindings(route, processed)
            return _PreparedRoute(params=processed, ordered=ordered_params, bindings=bindings)

        coerced = self._coerce_params(route, params)
        processed = run_preprocessors(
            route.preprocess,
            coerced,
            route=route,
            request=request,
            loader=self._plugin_loader,
        )
        ordered_params = self._ordered_from_processed(route, processed)
        bindings = self._build_bindings(route, processed)
        return _PreparedRoute(params=processed, ordered=ordered_params, bindings=bindings)

    def _coerce_params(
        self, route: RouteDefinition, provided: Mapping[str, object]
    ) -> MutableMapping[str, object | None]:
        values: MutableMapping[str, object | None] = {}
        remaining: MutableMapping[str, object] = dict(provided)
        for spec in route.params:
            if spec.name in remaining:
                raw = remaining.pop(spec.name)
                values[spec.name] = self._convert_value(spec, raw)
            else:
                if spec.default is not None:
                    values[spec.name] = spec.default
                elif spec.required:
                    raise RouteExecutionError(
                        f"Missing required parameter '{spec.name}' for route '{route.id}'"
                    )
                else:
                    values[spec.name] = None
        for key, value in remaining.items():
            values[key] = value
        return values

    def _convert_value(self, spec: ParameterSpec, raw: object) -> object | None:
        if raw is None:
            return None
        if isinstance(raw, str):
            try:
                return spec.convert(raw)
            except Exception as exc:  # pragma: no cover - defensive conversion guard
                raise RouteExecutionError(
                    f"Unable to convert value for parameter '{spec.name}'"
                ) from exc
        return raw

    def _ordered_from_processed(
        self, route: RouteDefinition, processed: Mapping[str, object]
    ) -> list[object | None]:
        ordered: list[object | None] = []
        for name in route.param_order:
            if name in processed:
                ordered.append(processed[name])
                continue
            spec = route.find_param(name)
            if spec is None:
                ordered.append(processed.get(name))
                continue
            if spec.default is not None:
                ordered.append(spec.default)
            elif spec.required:
                raise RouteExecutionError(
                    f"Missing required parameter '{name}' after preprocessing for route '{route.id}'"
                )
            else:
                ordered.append(None)
        return ordered

    def _build_bindings(
        self, route: RouteDefinition, processed: Mapping[str, object]
    ) -> Mapping[str, object]:
        bindings: dict[str, object] = {}
        seen: set[str] = set()
        for name in route.param_order:
            if name in seen:
                continue
            seen.add(name)
            if name in processed:
                bindings[name] = processed[name]
                continue
            spec = route.find_param(name)
            if spec is None:
                bindings[name] = processed.get(name)
                continue
            if spec.default is not None:
                bindings[name] = spec.default
            elif spec.required:
                raise RouteExecutionError(
                    f"Missing required parameter '{name}' after preprocessing for route '{route.id}'"
                )
            else:
                bindings[name] = None

        for name, value in route.constant_params.items():
            bindings[name] = value

        return bindings

    def _render_sql(
        self,
        route: RouteDefinition,
        prepared: _PreparedRoute,
        *,
        request: Request | None,
    ) -> str:
        sql = self._apply_template(route, prepared.params, request=request)
        self._enforce_file_function_rules(sql, route)
        return sql

    def _apply_template(
        self,
        route: RouteDefinition,
        params: Mapping[str, object],
        *,
        request: Request | None,
    ) -> str:
        sql = route.prepared_sql
        slots = getattr(route, "template_slots", ())
        if not slots:
            return sql
        rendered = sql
        for slot in slots:
            spec = route.find_param(slot.param)
            if spec is None:
                raise RouteExecutionError(
                    f"Template references unknown parameter '{slot.param}' in route '{route.id}'"
                )
            value = params.get(slot.param)
            if value is None:
                raise RouteExecutionError(
                    f"Template parameter '{slot.param}' was not provided for route '{route.id}'"
                )
            _evaluate_template_guard(spec, value, route.id)
            rendered_value = _apply_template_filters(value, slot.filters, spec, route.id)
            rendered = rendered.replace(slot.placeholder, rendered_value, 1)
        return rendered

    def _enforce_file_function_rules(self, sql: str, route: RouteDefinition) -> None:
        if not getattr(
            self._interpolation_config, "forbid_db_params_in_file_functions", False
        ):
            return
        for match in _FILE_FUNCTION_PATTERN.finditer(sql):
            args = match.group("args") or ""
            names = re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", args)
            for name in names:
                if name in route.constant_params:
                    continue
                func = match.group("func")
                raise RouteExecutionError(
                    f"DuckDB function '{func}' cannot bind parameter '${name}' in route '{route.id}'"
                )

    def _make_reader_factory(
        self,
        route: RouteDefinition,
        prepared: _PreparedRoute,
        *,
        request: Request | None,
    ) -> Callable[[], tuple[pa.RecordBatchReader, Callable[[], None]]]:
        def factory() -> tuple[pa.RecordBatchReader, Callable[[], None]]:
            con, cursor = self._connect_and_execute(route, prepared, request=request)
            try:
                reader = cursor.fetch_record_batch()
            except Exception:
                con.close()
                raise
            return reader, con.close

        return factory

    def _make_execute_fn(
        self,
        route: RouteDefinition,
        prepared: _PreparedRoute,
        *,
        request: Request | None,
    ) -> Callable[[], pa.Table]:
        def runner() -> pa.Table:
            con, cursor = self._connect_and_execute(route, prepared, request=request)
            try:
                return cursor.fetch_arrow_table()
            finally:
                con.close()

        return runner

    def _connect_and_execute(
        self,
        route: RouteDefinition,
        prepared: _PreparedRoute,
        *,
        request: Request | None,
    ) -> tuple[duckdb.DuckDBPyConnection, duckdb.DuckDBPyRelation]:
        con = duckdb.connect()
        try:
            self._register_dependencies(con, route, prepared.params, request=request)
            sql = self._render_sql(route, prepared, request=request)
            cursor = con.execute(sql, prepared.bindings)
            return con, cursor
        except Exception:
            con.close()
            raise

    def _register_dependencies(
        self,
        con: duckdb.DuckDBPyConnection,
        route: RouteDefinition,
        params: Mapping[str, object],
        *,
        request: Request | None,
    ) -> None:
        if not getattr(route, "uses", None):
            return
        for use in route.uses:
            self._register_dependency(con, route, params, use, request=request)

    def _register_dependency(
        self,
        con: duckdb.DuckDBPyConnection,
        route: RouteDefinition,
        params: Mapping[str, object],
        use: RouteUse,
        *,
        request: Request | None,
    ) -> None:
        target = self._routes.get(use.call)
        if target is None:
            raise RouteExecutionError(
                f"Route '{route.id}' references unknown dependency '{use.call}'"
            )
        handler = self._select_dependency_handler(use.mode)
        if handler is None:
            raise RouteExecutionError(
                f"Route '{route.id}' dependency '{use.alias}' uses unsupported mode '{use.mode}'"
            )
        resolved_args = self._resolve_dependency_args(use, params)
        prepared = self._prepare_dependency_route(target, resolved_args, request=request)
        handler(
            con,
            route,
            use,
            target,
            prepared,
            request=request,
        )

    def _resolve_dependency_args(
        self, use: RouteUse, params: Mapping[str, object]
    ) -> Mapping[str, object]:
        if not use.args:
            return {}
        resolved: dict[str, object] = {}
        for key, value in use.args.items():
            if isinstance(value, str) and value in params:
                resolved[key] = params[value]
            else:
                resolved[key] = value
        return resolved

    def _prepare_dependency_route(
        self,
        target: RouteDefinition,
        args: Mapping[str, object],
        *,
        request: Request | None,
    ) -> _PreparedRoute:
        return self._prepare(
            target,
            args,
            ordered=None,
            preprocessed=False,
            request=request,
        )

    def _select_dependency_handler(
        self, mode: str
    ) -> Callable[..., None] | None:
        mode_normalized = mode.lower()
        if mode_normalized == "relation":
            return self._handle_relation_dependency
        if mode_normalized == "parquet_path":
            return self._handle_parquet_dependency
        return None

    def _handle_relation_dependency(
        self,
        con: duckdb.DuckDBPyConnection,
        route: RouteDefinition,
        use: RouteUse,
        target: RouteDefinition,
        prepared: _PreparedRoute,
        *,
        request: Request | None,
    ) -> None:
        result = self._run_relation(target, prepared, offset=0, limit=None, request=request)
        con.register(use.alias, result.table)

    def _handle_parquet_dependency(
        self,
        con: duckdb.DuckDBPyConnection,
        route: RouteDefinition,
        use: RouteUse,
        target: RouteDefinition,
        prepared: _PreparedRoute,
        *,
        request: Request | None,
    ) -> None:
        try:
            artifacts = materialize_parquet_artifacts(
                target,
                prepared.params,
                prepared.bindings,
                store=self._cache_store,
                config=self._cache_config,
                reader_factory=self._make_reader_factory(target, prepared, request=request),
            )
        except RuntimeError as exc:
            raise RouteExecutionError(str(exc)) from exc
        if artifacts.paths:
            relation = con.read_parquet([str(path) for path in artifacts.paths])
            relation.create_view(use.alias, replace=True)
            return
        empty = pa.Table.from_batches([], schema=artifacts.schema)
        con.register(use.alias, empty)


__all__ = ["RouteExecutionError", "RouteExecutor"]
