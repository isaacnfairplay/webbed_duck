from __future__ import annotations

import importlib
import io
import time
from datetime import datetime
from typing import Callable, Iterable, Mapping, Sequence

import duckdb
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from ..config import Config
from ..core.routes import RouteDefinition
from ..plugins.charts import render_route_charts
from .analytics import AnalyticsStore
from .csv import append_record
from .auth import resolve_auth_adapter
from .meta import MetaStore, _utcnow
from .overlay import (
    OverlayStore,
    apply_overrides,
    compute_row_key_from_values,
)
from .postprocess import render_cards_html, render_feed_html, render_table_html, table_to_records
from .session import SESSION_COOKIE_NAME, SessionStore
from .share import ShareStore

EmailSender = Callable[[Sequence[str], str, str, str | None, Sequence[tuple[str, bytes]] | None], None]

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
    app.state.meta = MetaStore(config.server.storage_root)
    app.state.session_store = SessionStore(app.state.meta, config.auth)
    app.state.share_store = ShareStore(app.state.meta, config)
    app.state.email_sender = _load_email_sender(config.email.adapter)
    app.state.auth_adapter = resolve_auth_adapter(
        config.auth.mode,
        config=config,
        session_store=app.state.session_store,
    )

    for route in routes:
        app.add_api_route(
            route.path,
            endpoint=_make_endpoint(route),
            methods=list(route.methods),
            summary=route.title,
            description=route.description,
        )

    if config.auth.mode == "pseudo":
        @app.post("/auth/pseudo/session")
        async def create_pseudo_session(request: Request) -> Mapping[str, object]:
            payload = await request.json()
            if not isinstance(payload, Mapping):
                raise _http_error("invalid_parameter", "Session payload must be an object")
            email_raw = payload.get("email")
            remember = bool(payload.get("remember_me", False))
            try:
                email = app.state.session_store.validate_email(str(email_raw))
            except ValueError as exc:
                raise _http_error("invalid_parameter", str(exc)) from exc
            ip_address = request.client.host if request.client else None
            record = app.state.session_store.create(
                email=email,
                user_agent=request.headers.get("user-agent"),
                ip_address=ip_address,
                remember_me=remember,
            )
            response = JSONResponse(
                {
                    "user": {
                        "id": record.email,
                        "email_hash": record.email_hash,
                        "expires_at": record.expires_at.isoformat(),
                    }
                }
            )
            max_age = max(0, int((record.expires_at - _utcnow()).total_seconds()))
            response.set_cookie(
                SESSION_COOKIE_NAME,
                record.token,
                httponly=True,
                max_age=max_age,
                samesite="lax",
            )
            return response

        @app.get("/auth/pseudo/session")
        async def get_pseudo_session(request: Request) -> Mapping[str, object]:
            user = await app.state.auth_adapter.authenticate(request)
            if not user:
                raise HTTPException(status_code=401, detail={"code": "not_authenticated", "message": "Session not found"})
            return {
                "user": {
                    "id": user.user_id,
                    "email_hash": user.email_hash,
                    "display_name": user.display_name,
                }
            }

        @app.delete("/auth/pseudo/session")
        async def delete_pseudo_session(request: Request) -> Mapping[str, object]:
            token = request.cookies.get(SESSION_COOKIE_NAME)
            if token:
                app.state.session_store.destroy(token)
            response = JSONResponse({"deleted": True})
            response.delete_cookie(SESSION_COOKIE_NAME)
            return response

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

    @app.post("/routes/{route_id}/share")
    async def create_share(route_id: str, request: Request) -> Mapping[str, object]:
        route = _get_route(app.state.routes, route_id)
        user = await app.state.auth_adapter.authenticate(request)
        if not user:
            raise HTTPException(status_code=401, detail={"code": "not_authenticated", "message": "Login required to create shares"})
        payload = await request.json()
        if not isinstance(payload, Mapping):
            raise _http_error("invalid_parameter", "Share payload must be an object")
        fmt = (payload.get("format") or "html_t").lower()
        fmt = _validate_format(fmt)
        params_raw = payload.get("params") or {}
        if not isinstance(params_raw, Mapping):
            raise _http_error("invalid_parameter", "Share params must be an object")
        try:
            params = _prepare_share_params(route, params_raw)
        except ValueError as exc:
            raise _http_error("invalid_parameter", str(exc)) from exc
        recipients_raw = payload.get("emails") or payload.get("recipients")
        if not isinstance(recipients_raw, Sequence):
            raise _http_error("invalid_parameter", "Share requires a list of recipient emails")
        recipients = [str(item).strip().lower() for item in recipients_raw if str(item).strip()]
        if not recipients:
            raise _http_error("invalid_parameter", "At least one recipient email is required")
        share = app.state.share_store.create(
            route.id,
            params=params,
            fmt=fmt,
            created_by_hash=user.email_hash,
            request=request,
        )
        share_url = str(request.url_for("resolve_share", token=share.token))
        if app.state.email_sender is not None:
            subject = f"{route.title or route.id} shared with you"
            html_body, text_body = _render_share_email(route, share_url, share.expires_at, user)
            try:
                app.state.email_sender(recipients, subject, html_body, text_body, None)
            except Exception as exc:  # pragma: no cover - adapter errors vary
                raise HTTPException(status_code=502, detail={"code": "email_failed", "message": str(exc)}) from exc
        return {
            "share": {
                "token": share.token,
                "expires_at": share.expires_at.isoformat(),
                "url": share_url,
                "format": fmt,
            }
        }

    @app.get("/shares/{token}", name="resolve_share")
    async def resolve_share(token: str, request: Request) -> Response:
        record = app.state.share_store.resolve(token, request)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "share_not_found", "message": "Share link is invalid or expired"})
        fmt = _validate_format((request.query_params.get("format") or record.format).lower())
        limit = _parse_optional_int(request.query_params.get("limit"))
        offset = _parse_optional_int(request.query_params.get("offset"))
        columns = request.query_params.getlist("column")
        return _render_route_response(
            _get_route(app.state.routes, record.route_id),
            request,
            record.params,
            fmt,
            limit,
            offset,
            columns,
            record_analytics=False,
        )

    return app


def _make_endpoint(route: RouteDefinition):
    async def endpoint(request: Request) -> Response:
        params = _collect_params(route, request)
        limit = _parse_optional_int(request.query_params.get("limit"))
        offset = _parse_optional_int(request.query_params.get("offset"))
        columns = request.query_params.getlist("column")
        fmt = (request.query_params.get("format") or "json").lower()

        return _render_route_response(
            route,
            request,
            params,
            fmt,
            limit,
            offset,
            columns,
            record_analytics=True,
        )

    return endpoint


def _render_route_response(
    route: RouteDefinition,
    request: Request,
    params: Mapping[str, object],
    fmt: str,
    limit: int | None,
    offset: int | None,
    columns: Sequence[str],
    *,
    record_analytics: bool,
) -> Response:
    fmt = _validate_format(fmt)
    ordered = [_value_for_name(params, name, route) for name in route.param_order]
    start = time.perf_counter()
    try:
        table = _execute_sql(route.prepared_sql, ordered)
    except duckdb.Error as exc:  # pragma: no cover - safety net
        raise HTTPException(status_code=500, detail={"code": "duckdb_error", "message": str(exc)}) from exc
    elapsed_ms = (time.perf_counter() - start) * 1000

    metadata = route.metadata if isinstance(route.metadata, Mapping) else {}
    table = apply_overrides(table, metadata, request.app.state.overlays.list_for_route(route.id))
    table = _select_columns(table, columns)
    table, total_rows, applied_offset, applied_limit = _apply_slice(table, offset, limit)

    if record_analytics:
        request.app.state.analytics.record(route.id)

    charts_meta: list[dict[str, str]] = []
    if metadata:
        charts_meta = render_route_charts(table, metadata.get("charts", []))

    return _format_response(
        table,
        fmt,
        route,
        metadata,
        request,
        charts_meta,
        elapsed_ms,
        total_rows,
        applied_offset,
        applied_limit,
    )


def _validate_format(fmt: str) -> str:
    allowed = {"json", "table", "html_t", "html_c", "feed", "arrow", "arrow_rpc", "csv", "parquet"}
    if fmt not in allowed:
        raise _http_error("invalid_parameter", f"Unsupported format '{fmt}'")
    return fmt


def _select_columns(table: pa.Table, columns: Sequence[str]) -> pa.Table:
    if not columns:
        return table
    selectable = [col for col in columns if col in table.column_names]
    if not selectable:
        return table
    return table.select(selectable)


def _apply_slice(
    table: pa.Table,
    offset: int | None,
    limit: int | None,
) -> tuple[pa.Table, int, int, int | None]:
    total = table.num_rows
    start_idx = max(0, offset or 0)
    if start_idx >= total:
        return table.slice(total, 0), total, total, 0
    if limit is None:
        return table.slice(start_idx, total - start_idx), total, start_idx, None
    length = max(0, min(limit, total - start_idx))
    return table.slice(start_idx, length), total, start_idx, limit


def _format_response(
    table: pa.Table,
    fmt: str,
    route: RouteDefinition,
    metadata: Mapping[str, object],
    request: Request,
    charts_meta: Sequence[Mapping[str, object]],
    elapsed_ms: float,
    total_rows: int,
    offset: int,
    limit: int | None,
) -> Response:
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
            "total_rows": total_rows,
            "offset": offset,
            "limit": limit,
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
    if fmt == "arrow":
        return _arrow_stream_response(table)
    if fmt == "arrow_rpc":
        response = _arrow_stream_response(table)
        response.headers["x-total-rows"] = str(total_rows)
        response.headers["x-offset"] = str(offset)
        response.headers["x-limit"] = str(limit if limit is not None else total_rows)
        return response
    if fmt == "csv":
        return _csv_response(route, table)
    if fmt == "parquet":
        return _parquet_response(route, table)
    raise _http_error("invalid_parameter", f"Unsupported format '{fmt}'")


def _csv_response(route: RouteDefinition, table: pa.Table) -> StreamingResponse:
    sink = pa.BufferOutputStream()
    pacsv.write_csv(table, sink)
    buffer = sink.getvalue().to_pybytes()
    stream = io.BytesIO(buffer)
    response = StreamingResponse(stream, media_type="text/csv")
    response.headers["content-disposition"] = f'attachment; filename="{route.id}.csv"'
    return response


def _parquet_response(route: RouteDefinition, table: pa.Table) -> StreamingResponse:
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink)
    buffer = sink.getvalue().to_pybytes()
    stream = io.BytesIO(buffer)
    response = StreamingResponse(stream, media_type="application/x-parquet")
    response.headers["content-disposition"] = f'attachment; filename="{route.id}.parquet"'
    return response


def _prepare_share_params(route: RouteDefinition, raw: Mapping[str, object]) -> Mapping[str, object]:
    values: dict[str, object] = {}
    for spec in route.params:
        if spec.name in raw:
            incoming = raw[spec.name]
            if incoming is None:
                if spec.required and spec.default is None:
                    raise ValueError(f"Missing required parameter '{spec.name}' for share")
                values[spec.name] = None
                continue
            try:
                if isinstance(incoming, str):
                    values[spec.name] = spec.convert(incoming)
                else:
                    values[spec.name] = spec.convert(str(incoming))
            except Exception as exc:  # pragma: no cover - conversion safety
                raise ValueError(f"Invalid value for parameter '{spec.name}'") from exc
        else:
            if spec.default is not None:
                values[spec.name] = spec.default
            elif spec.required:
                raise ValueError(f"Missing required parameter '{spec.name}' for share")
            else:
                values[spec.name] = None
    return values


def _render_share_email(route: RouteDefinition, url: str, expires_at: datetime, user) -> tuple[str, str]:
    title = route.title or route.id
    creator = getattr(user, "display_name", None) or getattr(user, "user_id", "webbed_duck")
    expires = expires_at.isoformat()
    html = (
        "<!doctype html><meta charset='utf-8'>"
        f"<h3>{title}</h3>"
        f"<p>{creator} shared a view with you.</p>"
        f"<p><a href='{url}'>Open the share</a></p>"
        f"<p>This link expires at {expires}.</p>"
    )
    text = f"{title} shared by {creator}. Access: {url} (expires {expires})."
    return html, text


def _load_email_sender(path: str | None) -> EmailSender | None:
    if not path:
        return None
    module_name, _, attr = path.partition(":")
    if not attr:
        module_name, attr = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    sender = getattr(module, attr)
    if not callable(sender):
        raise TypeError("Email adapter must be callable")
    return sender


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
