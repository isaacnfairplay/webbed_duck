"""Utilities for executing compiled routes with dependency resolution."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, MutableMapping, Sequence

import duckdb
import pyarrow as pa

from ..config import Config
from ..core.routes import ParameterSpec, RouteDefinition, RouteUse
from .cache import (
    CacheQueryResult,
    CacheStore,
    fetch_cached_table,
    materialize_parquet_artifacts,
)
from .preprocess import run_preprocessors


class RouteExecutionError(RuntimeError):
    """Raised when a route or dependency cannot be executed."""


@dataclass(slots=True)
class _PreparedRoute:
    params: Mapping[str, object]
    ordered: Sequence[object]


class RouteExecutor:
    """Execute routes while honoring declarative dependencies."""

    def __init__(
        self,
        routes_by_id: Mapping[str, RouteDefinition],
        *,
        cache_store: CacheStore | None,
        config: Config,
    ) -> None:
        self._routes = dict(routes_by_id)
        self._cache_store = cache_store
        self._cache_config = config.cache
        self._stack: list[str] = []

    def execute_relation(
        self,
        route: RouteDefinition,
        params: Mapping[str, object],
        *,
        ordered: Sequence[object] | None = None,
        preprocessed: bool = False,
        offset: int = 0,
        limit: int | None = None,
    ) -> CacheQueryResult:
        prepared = self._prepare(route, params, ordered=ordered, preprocessed=preprocessed)
        return self._run_relation(route, prepared, offset=offset, limit=limit)

    def _run_relation(
        self,
        route: RouteDefinition,
        prepared: _PreparedRoute,
        *,
        offset: int,
        limit: int | None,
    ) -> CacheQueryResult:
        if route.id in self._stack:
            raise RouteExecutionError(f"Circular dependency detected while executing route '{route.id}'")
        self._stack.append(route.id)
        try:
            reader_factory = self._make_reader_factory(route, prepared)
            execute_sql = self._make_execute_fn(route, prepared)
            return fetch_cached_table(
                route,
                prepared.params,
                prepared.ordered,
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
    ) -> _PreparedRoute:
        if preprocessed:
            processed = dict(params)
            ordered_params = list(ordered) if ordered is not None else self._ordered_from_processed(route, processed)
            return _PreparedRoute(params=processed, ordered=ordered_params)

        coerced = self._coerce_params(route, params)
        processed = run_preprocessors(route.preprocess, coerced, route=route, request=None)
        ordered_params = self._ordered_from_processed(route, processed)
        return _PreparedRoute(params=processed, ordered=ordered_params)

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

    def _make_reader_factory(
        self, route: RouteDefinition, prepared: _PreparedRoute
    ) -> Callable[[], tuple[pa.RecordBatchReader, Callable[[], None]]]:
        def factory() -> tuple[pa.RecordBatchReader, Callable[[], None]]:
            con = duckdb.connect()
            try:
                self._register_dependencies(con, route, prepared.params)
                cursor = con.execute(route.prepared_sql, prepared.ordered)
                reader = cursor.fetch_record_batch()
            except Exception:
                con.close()
                raise
            return reader, con.close

        return factory

    def _make_execute_fn(
        self, route: RouteDefinition, prepared: _PreparedRoute
    ) -> Callable[[], pa.Table]:
        def runner() -> pa.Table:
            con = duckdb.connect()
            try:
                self._register_dependencies(con, route, prepared.params)
                cursor = con.execute(route.prepared_sql, prepared.ordered)
                return cursor.fetch_arrow_table()
            finally:
                con.close()

        return runner

    def _register_dependencies(
        self,
        con: duckdb.DuckDBPyConnection,
        route: RouteDefinition,
        params: Mapping[str, object],
    ) -> None:
        if not getattr(route, "uses", None):
            return
        for use in route.uses:
            self._register_dependency(con, route, params, use)

    def _register_dependency(
        self,
        con: duckdb.DuckDBPyConnection,
        route: RouteDefinition,
        params: Mapping[str, object],
        use: RouteUse,
    ) -> None:
        target = self._routes.get(use.call)
        if target is None:
            raise RouteExecutionError(
                f"Route '{route.id}' references unknown dependency '{use.call}'"
            )
        resolved_args = self._resolve_dependency_args(use, params)
        if use.mode == "relation":
            prepared = self._prepare(target, resolved_args, ordered=None, preprocessed=False)
            result = self._run_relation(target, prepared, offset=0, limit=None)
            con.register(use.alias, result.table)
            return
        if use.mode == "parquet_path":
            prepared = self._prepare(target, resolved_args, ordered=None, preprocessed=False)
            try:
                artifacts = materialize_parquet_artifacts(
                    target,
                    prepared.params,
                    prepared.ordered,
                    store=self._cache_store,
                    config=self._cache_config,
                    reader_factory=self._make_reader_factory(target, prepared),
                )
            except RuntimeError as exc:
                raise RouteExecutionError(str(exc)) from exc
            if artifacts.paths:
                relation = con.read_parquet([str(path) for path in artifacts.paths])
                relation.create_view(use.alias, replace=True)
            else:
                empty = pa.Table.from_batches([], schema=artifacts.schema)
                con.register(use.alias, empty)
            return
        raise RouteExecutionError(
            f"Route '{route.id}' dependency '{use.alias}' uses unsupported mode '{use.mode}'"
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


__all__ = ["RouteExecutionError", "RouteExecutor"]
