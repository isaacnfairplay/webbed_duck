"""FastAPI application factory for webbed_duck."""
from __future__ import annotations

import time
from typing import Iterable, Mapping, Sequence

import duckdb
from fastapi import FastAPI, HTTPException, Request

from ..config import Config
from ..core.routes import RouteDefinition


def create_app(routes: Sequence[RouteDefinition], config: Config) -> FastAPI:
    if not routes:
        raise ValueError("At least one route must be provided to create the application")

    app = FastAPI(title="webbed_duck", version="0.1.0")
    app.state.config = config

    for route in routes:
        app.add_api_route(
            route.path,
            endpoint=_make_endpoint(route),
            methods=list(route.methods),
            summary=route.title,
            description=route.description,
        )

    return app


def _make_endpoint(route: RouteDefinition):
    async def endpoint(request: Request) -> Mapping[str, object]:
        params = _collect_params(route, request)
        ordered = [_value_for_name(params, name, route) for name in route.param_order]
        start = time.perf_counter()
        table = _execute_sql(route.prepared_sql, ordered)
        elapsed_ms = (time.perf_counter() - start) * 1000
        rows = table.to_pylist()
        return {
            "route_id": route.id,
            "title": route.title,
            "description": route.description,
            "row_count": len(rows),
            "columns": table.column_names,
            "rows": rows,
            "elapsed_ms": round(elapsed_ms, 3),
        }

    return endpoint


def _collect_params(route: RouteDefinition, request: Request) -> Mapping[str, object]:
    values: dict[str, object] = {}
    for spec in route.params:
        raw_value = request.query_params.get(spec.name)
        if raw_value is None:
            if spec.default is not None:
                values[spec.name] = spec.default
            elif spec.required:
                raise HTTPException(status_code=400, detail=f"Missing required parameter '{spec.name}'")
            else:
                values[spec.name] = None
            continue
        try:
            values[spec.name] = spec.convert(raw_value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return values


def _value_for_name(values: Mapping[str, object], name: str, route: RouteDefinition) -> object:
    if name not in values:
        spec = route.find_param(name)
        if spec is None:
            raise HTTPException(status_code=400, detail=f"Parameter '{name}' not defined for route '{route.id}'")
        if spec.default is not None:
            return spec.default
        if spec.required:
            raise HTTPException(status_code=400, detail=f"Missing required parameter '{name}'")
        return None
    return values[name]


def _execute_sql(sql: str, params: Iterable[object]):
    con = duckdb.connect()
    try:
        cursor = con.execute(sql, params)
        return cursor.fetch_arrow_table()
    finally:
        con.close()


__all__ = ["create_app"]
