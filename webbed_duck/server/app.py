from __future__ import annotations

import io
import time
from typing import Iterable, Mapping, Sequence

import duckdb
import pyarrow as pa
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from ..config import Config
from ..core.routes import RouteDefinition
from ..plugins.charts import render_route_charts
from .analytics import AnalyticsStore
from .postprocess import render_cards_html, render_feed_html, render_table_html, table_to_records

_ERROR_TAXONOMY = {
    "missing_parameter": {
        "message": "A required parameter was not provided.",
        "hint": "Ensure the query string includes the documented parameter name.",
    },
    "invalid_parameter": {
        "message": "A parameter value could not be converted to the expected type.",
        "hint": "Verify the value is formatted as documented (e.g. integer, boolean).",
    },
    "unknown_parameter": {
        "message": "The query referenced an undefined parameter.",
        "hint": "Recompile routes or check the metadata for available parameters.",
    },
}


def create_app(routes: Sequence[RouteDefinition], config: Config) -> FastAPI:
    if not routes:
        raise ValueError("At least one route must be provided to create the application")

    app = FastAPI(title="webbed_duck", version="0.2.0")
    app.state.config = config
    app.state.analytics = AnalyticsStore(weight=config.analytics.weight_interactions)
    app.state.routes = list(routes)

    for route in routes:
        app.add_api_route(
            route.path,
            endpoint=_make_endpoint(route),
            methods=list(route.methods),
            summary=route.title,
            description=route.description,
        )

    @app.get("/routes")
    async def list_routes(folder: str | None = None) -> Mapping[str, object]:
        stats = app.state.analytics.snapshot()
        subset: list[Mapping[str, object]] = []
        prefix = folder or ""
        for route in app.state.routes:
            if prefix and not route.path.startswith(prefix):
                continue
            subset.append(
                {
                    "id": route.id,
                    "path": route.path,
                    "title": route.title,
                    "description": route.description,
                    "popularity": stats.get(route.id, 0),
                }
            )
        subset.sort(key=lambda item: (-item["popularity"], item["path"]))
        return {"folder": prefix or "/", "routes": subset}

    return app


def _make_endpoint(route: RouteDefinition):
    async def endpoint(request: Request) -> Response:
        params = _collect_params(route, request)
        ordered = [_value_for_name(params, name, route) for name in route.param_order]
        limit = _parse_optional_int(request.query_params.get("limit"))
        offset = _parse_optional_int(request.query_params.get("offset"))
        columns = request.query_params.getlist("column")
        fmt = (request.query_params.get("format") or "json").lower()

        start = time.perf_counter()
        try:
            table = _execute_sql(route.prepared_sql, ordered)
        except duckdb.Error as exc:  # pragma: no cover - safety net
            raise HTTPException(status_code=500, detail={"code": "duckdb_error", "message": str(exc)}) from exc
        elapsed_ms = (time.perf_counter() - start) * 1000

        if columns:
            selectable = [col for col in columns if col in table.column_names]
            if selectable:
                table = table.select(selectable)
        if offset or limit:
            start_idx = max(0, offset or 0)
            total = table.num_rows
            if start_idx >= total:
                table = table.slice(total, 0)
            else:
                if limit is None:
                    length = total - start_idx
                else:
                    length = max(0, min(limit, total - start_idx))
                table = table.slice(start_idx, length)

        request.app.state.analytics.record(route.id)

        charts_meta: list[dict[str, str]] = []
        metadata = route.metadata if isinstance(route.metadata, Mapping) else {}
        if metadata:
            charts_meta = render_route_charts(table, metadata.get("charts", []))

        if fmt in {"json", "table"}:
            records = table_to_records(table)
            payload = {
                "route_id": route.id,
                "title": route.title,
                "description": route.description,
                "row_count": len(records),
                "columns": table.column_names,
                "rows": records,
                "elapsed_ms": round(elapsed_ms, 3),
                "charts": charts_meta,
            }
            return JSONResponse(payload)
        if fmt == "html_t":
            html = render_table_html(table, metadata, request.app.state.config, charts_meta)
            return HTMLResponse(html)
        if fmt == "html_c":
            html = render_cards_html(table, metadata, request.app.state.config, charts_meta)
            return HTMLResponse(html)
        if fmt == "feed":
            html = render_feed_html(table, metadata, request.app.state.config)
            return HTMLResponse(html)
        if fmt in {"arrow", "arrow_rpc"}:
            return _arrow_stream_response(table)

        raise _http_error("invalid_parameter", f"Unsupported format '{fmt}'")

    return endpoint


def _collect_params(route: RouteDefinition, request: Request) -> Mapping[str, object]:
    values: dict[str, object] = {}
    for spec in route.params:
        raw_value = request.query_params.get(spec.name)
        if raw_value is None:
            if spec.default is not None:
                values[spec.name] = spec.default
            elif spec.required:
                raise _http_error("missing_parameter", f"Missing required parameter '{spec.name}'")
            else:
                values[spec.name] = None
            continue
        try:
            values[spec.name] = spec.convert(raw_value)
        except ValueError as exc:
            raise _http_error("invalid_parameter", str(exc)) from exc
    return values


def _value_for_name(values: Mapping[str, object], name: str, route: RouteDefinition) -> object:
    if name not in values:
        spec = route.find_param(name)
        if spec is None:
            raise _http_error("unknown_parameter", f"Parameter '{name}' not defined for route '{route.id}'")
        if spec.default is not None:
            return spec.default
        if spec.required:
            raise _http_error("missing_parameter", f"Missing required parameter '{name}'")
        return None
    return values[name]


def _execute_sql(sql: str, params: Iterable[object]) -> pa.Table:
    con = duckdb.connect()
    try:
        cursor = con.execute(sql, params)
        return cursor.fetch_arrow_table()
    finally:
        con.close()


def _arrow_stream_response(table: pa.Table) -> StreamingResponse:
    sink = io.BytesIO()
    with pa.ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    sink.seek(0)
    return StreamingResponse(sink, media_type="application/vnd.apache.arrow.stream")


def _parse_optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise _http_error("invalid_parameter", f"Expected an integer but received '{value}'") from exc


def _http_error(code: str, message: str) -> HTTPException:
    entry = _ERROR_TAXONOMY.get(code, {})
    detail = {"code": code, "message": message}
    hint = entry.get("hint")
    if hint:
        detail["hint"] = hint
    return HTTPException(status_code=400, detail=detail)


__all__ = ["create_app"]
