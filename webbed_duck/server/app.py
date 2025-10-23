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
from .csv import append_record
from .auth import resolve_auth_adapter
from .overlay import (
    OverlayStore,
    apply_overrides,
    compute_row_key_from_values,
)
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

    app = FastAPI(title="webbed_duck", version="0.3.0")
    app.state.config = config
    app.state.analytics = AnalyticsStore(weight=config.analytics.weight_interactions)
    app.state.routes = list(routes)
    app.state.overlays = OverlayStore(config.server.storage_root)
    app.state.auth_adapter = resolve_auth_adapter(config.auth.mode)

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

    @app.get("/routes/{route_id}/schema")
    async def describe_route(route_id: str, request: Request) -> Mapping[str, object]:
        route = _get_route(app.state.routes, route_id)
        params = _collect_params(route, request)
        ordered = [_value_for_name(params, name, route) for name in route.param_order]
        table = _execute_sql(_limit_zero(route.prepared_sql), ordered)
        schema = [
            {"name": field.name, "type": str(field.type)}
            for field in table.schema
        ]
        form = [
            {
                "name": spec.name,
                "type": spec.type.value,
                "required": spec.required,
                "default": spec.default,
                "description": spec.description,
            }
            for spec in route.params
        ]
        metadata = route.metadata if isinstance(route.metadata, Mapping) else {}
        return {
            "route_id": route.id,
            "path": route.path,
            "schema": schema,
            "form": form,
            "overrides": metadata.get("overrides", {}),
            "append": metadata.get("append", {}),
        }

    @app.get("/routes/{route_id}/overrides")
    async def list_overrides(route_id: str) -> Mapping[str, object]:
        route = _get_route(app.state.routes, route_id)
        overrides = [record.to_dict() for record in app.state.overlays.list_for_route(route.id)]
        return {"route_id": route.id, "overrides": overrides}

    @app.post("/routes/{route_id}/overrides")
    async def save_override(route_id: str, request: Request) -> Mapping[str, object]:
        route = _get_route(app.state.routes, route_id)
        metadata = route.metadata if isinstance(route.metadata, Mapping) else {}
        override_meta = metadata.get("overrides", {}) if isinstance(metadata, Mapping) else {}
        allowed = set(_coerce_sequence(override_meta.get("allowed")))
        key_columns = _coerce_sequence(override_meta.get("key_columns"))
        payload = await request.json()
        if not isinstance(payload, Mapping):
            raise _http_error("invalid_parameter", "Override payload must be an object")
        column = str(payload.get("column", "")).strip()
        if not column:
            raise _http_error("invalid_parameter", "Override column is required")
        if allowed and column not in allowed:
            raise HTTPException(status_code=403, detail={"code": "forbidden_override", "message": "Column cannot be overridden"})
        value = payload.get("value")
        reason = payload.get("reason")
        author = payload.get("author")
        row_key = payload.get("row_key")
        key_values = payload.get("key")
        if row_key is None:
            if not isinstance(key_values, Mapping):
                raise _http_error("missing_parameter", "Provide either row_key or key mapping")
            try:
                row_key = compute_row_key_from_values(key_values, key_columns)
            except KeyError as exc:
                raise _http_error("missing_parameter", str(exc)) from exc
        user = await app.state.auth_adapter.authenticate(request)
        record = app.state.overlays.upsert(
            route_id=route.id,
            row_key=str(row_key),
            column=column,
            value=value,
            reason=str(reason) if reason is not None else None,
            author=str(author) if author is not None else None,
            author_user_id=user.user_id if user else None,
        )
        return {"override": record.to_dict()}

    @app.post("/routes/{route_id}/append")
    async def append_route(route_id: str, request: Request) -> Mapping[str, object]:
        route = _get_route(app.state.routes, route_id)
        metadata = route.metadata if isinstance(route.metadata, Mapping) else {}
        append_meta = metadata.get("append") if isinstance(metadata, Mapping) else None
        if not isinstance(append_meta, Mapping):
            raise HTTPException(status_code=404, detail={"code": "append_not_configured", "message": "Route does not allow CSV append"})
        columns = _coerce_sequence(append_meta.get("columns"))
        if not columns:
            raise HTTPException(status_code=500, detail={"code": "append_misconfigured", "message": "Append metadata must declare columns"})
        destination = str(append_meta.get("destination") or f"{route.id}.csv")
        payload = await request.json()
        if not isinstance(payload, Mapping):
            raise _http_error("invalid_parameter", "Append payload must be an object")
        record = {column: payload.get(column) for column in columns}
        try:
            path = append_record(
                app.state.config.server.storage_root,
                destination=destination,
                columns=columns,
                record=record,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=500,
                detail={"code": "append_misconfigured", "message": str(exc)},
            ) from exc
        return {"appended": True, "path": str(path)}

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

        table = apply_overrides(table, route.metadata, request.app.state.overlays.list_for_route(route.id))

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


def _limit_zero(sql: str) -> str:
    inner = sql.strip().rstrip(";")
    return f"SELECT * FROM ({inner}) WHERE 1=0"


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


def _coerce_sequence(value: object) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item) for item in value]
    return []


def _get_route(routes: Sequence[RouteDefinition], route_id: str) -> RouteDefinition:
    for route in routes:
        if route.id == route_id:
            return route
    raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"Route '{route_id}' not found"})


def _http_error(code: str, message: str) -> HTTPException:
    entry = _ERROR_TAXONOMY.get(code, {})
    detail = {"code": code, "message": message}
    hint = entry.get("hint")
    if hint:
        detail["hint"] = hint
    return HTTPException(status_code=400, detail=detail)


__all__ = ["create_app"]
