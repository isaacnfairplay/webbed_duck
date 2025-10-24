from __future__ import annotations

import html
import io
import time
from typing import Iterable, Mapping, Sequence

import duckdb
import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.parquet as pa_parquet
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
from .share import ShareError, ShareStore
from .postprocess import render_cards_html, render_feed_html, render_table_html, table_to_records
from .email import build_share_attachments, load_email_adapter, normalize_recipients

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
    app.state.shares = ShareStore(config.server.storage_root)
    app.state.email_sender = load_email_adapter(config.email.adapter)
    adapter = resolve_auth_adapter(config)
    app.state.auth_adapter = adapter
    adapter.register_routes(app)

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

    @app.post("/shares")
    async def create_share(request: Request) -> Mapping[str, object]:
        user = await app.state.auth_adapter.authenticate(request)
        if user is None:
            raise HTTPException(status_code=401, detail={"code": "unauthenticated", "message": "Authentication required"})
        payload = await request.json()
        if not isinstance(payload, Mapping):
            raise _http_error("invalid_parameter", "Share payload must be an object")
        route_id = str(payload.get("route_id", "")).strip()
        if not route_id:
            raise _http_error("missing_parameter", "route_id is required")
        route = _get_route(app.state.routes, route_id)
        params_payload = payload.get("params") or {}
        if not isinstance(params_payload, Mapping):
            raise _http_error("invalid_parameter", "params must be an object if provided")
        params = _normalize_params(route, params_payload)
        ordered = [_value_for_name(params, name, route) for name in route.param_order]
        table = _execute_sql(route.prepared_sql, ordered)
        table = apply_overrides(table, route.metadata, request.app.state.overlays.list_for_route(route.id))
        records = table_to_records(table)
        metadata = route.metadata if isinstance(route.metadata, Mapping) else {}
        charts_meta = render_route_charts(table, metadata.get("charts", [])) if metadata else []
        share_payload = {
            "columns": table.column_names,
            "rows": records,
            "row_count": len(records),
            "charts": charts_meta,
        }
        token = request.app.state.shares.create_share(
            route_id=route.id,
            params=params,
            payload=share_payload,
            ttl_minutes=request.app.state.config.email.share_token_ttl_minutes,
            bind_user_agent=request.app.state.config.email.bind_share_to_user_agent,
            bind_ip_prefix=request.app.state.config.email.bind_share_to_ip_prefix,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
            owner_user_id=user.user_id,
            owner_email_hash=user.email_hash,
        )
        request.app.state.shares.prune_expired()

        email_status: Mapping[str, object] | None = None
        email_payload = payload.get("email")
        if email_payload is not None:
            sender = request.app.state.email_sender
            if sender is None:
                raise HTTPException(status_code=400, detail={"code": "email_not_configured", "message": "Email adapter is not configured"})
            if not isinstance(email_payload, Mapping):
                raise _http_error("invalid_parameter", "email must be an object")
            recipients = normalize_recipients(email_payload.get("to") or email_payload.get("recipients"))
            if not recipients:
                raise _http_error("missing_parameter", "email.to must include at least one recipient")
            subject = str(email_payload.get("subject") or f"Share link for {route.title or route.id}")
            message = str(email_payload.get("message") or "A share link has been created for you.")
            base_url = str(email_payload.get("base_url") or "").strip()
            share_url = f"{base_url.rstrip('/')}/shares/{token.token}" if base_url else f"/shares/{token.token}"
            attachments_spec = email_payload.get("attachments")
            if attachments_spec is None:
                formats = ["csv"]
            elif isinstance(attachments_spec, str):
                formats = [attachments_spec.lower()]
            elif isinstance(attachments_spec, Sequence):
                formats = [str(item).lower() for item in attachments_spec]
            else:
                raise _http_error("invalid_parameter", "email.attachments must be a string or list of strings")
            zip_passphrase = email_payload.get("zip_passphrase")
            if zip_passphrase is not None:
                zip_passphrase = str(zip_passphrase)
            watermark_text = f"Share for route {route.id} minted by {user.email or user.user_id}"
            try:
                attachments = build_share_attachments(
                    table,
                    route_id=route.id,
                    formats=formats,
                    config=request.app.state.config.share,
                    watermark_text=watermark_text,
                    zip_passphrase=zip_passphrase,
                )
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail={"code": "share_email_error", "message": str(exc)}) from exc
            table_html = render_table_html(table, metadata, request.app.state.config, charts_meta)
            html_body = (
                f"<p>{html.escape(message)}</p>"
                + f"<p><a href=\"{share_url}\">Open shared data</a></p>"
                + table_html
            )
            text_body = f"{message}\n\nLink: {share_url}"
            try:
                sender(recipients, subject, html_body, text_body, attachments)
            except Exception as exc:  # pragma: no cover - adapter failures
                raise HTTPException(status_code=502, detail={"code": "email_failed", "message": str(exc)}) from exc
            email_status = {"recipients": recipients, "share_url": share_url, "subject": subject}

        return {
            "share": {
                "token": token.token,
                "expires_at": token.expires_at,
                "route_id": route.id,
                "row_count": len(records),
                "email": email_status,
            }
        }

    @app.get("/shares/{token}")
    async def redeem_share(token: str, request: Request) -> Mapping[str, object]:
        try:
            record = request.app.state.shares.consume_share(
                token,
                user_agent=request.headers.get("user-agent"),
                ip_address=request.client.host if request.client else None,
            )
        except ShareError as exc:
            raise HTTPException(status_code=403, detail={"code": exc.code, "message": str(exc)}) from exc
        route = _get_route(app.state.routes, record.route_id)
        payload = record.payload
        rows = list(payload.get("rows", []))
        charts = list(payload.get("charts", []))
        return {
            "route_id": record.route_id,
            "title": route.title,
            "description": route.description,
            "columns": list(payload.get("columns", [])),
            "rows": rows,
            "row_count": payload.get("row_count", len(rows)),
            "charts": charts,
            "expires_at": record.expires_at,
            "uses": record.uses,
            "max_uses": record.max_uses,
        }

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
        if fmt == "csv":
            return _csv_response(table, route.id)
        if fmt == "parquet":
            return _parquet_response(table, route.id)
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


def _normalize_params(route: RouteDefinition, payload: Mapping[str, object]) -> dict[str, object]:
    values: dict[str, object] = {}
    for spec in route.params:
        if spec.name not in payload:
            if spec.default is not None:
                values[spec.name] = spec.default
            elif spec.required:
                raise _http_error("missing_parameter", f"Missing required parameter '{spec.name}'")
            else:
                values[spec.name] = None
            continue
        raw_value = payload[spec.name]
        if raw_value is None:
            values[spec.name] = None
            continue
        if isinstance(raw_value, bool):
            raw_text = "true" if raw_value else "false"
        else:
            raw_text = str(raw_value)
        try:
            values[spec.name] = spec.convert(raw_text)
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


def _csv_response(table: pa.Table, route_id: str) -> StreamingResponse:
    sink = pa.BufferOutputStream()
    pa_csv.write_csv(table, sink)
    buffer = io.BytesIO(sink.getvalue().to_pybytes())
    headers = {"content-disposition": f"attachment; filename={route_id}.csv"}
    return StreamingResponse(buffer, media_type="text/csv", headers=headers)


def _parquet_response(table: pa.Table, route_id: str) -> StreamingResponse:
    sink = pa.BufferOutputStream()
    pa_parquet.write_table(table, sink)
    buffer = io.BytesIO(sink.getvalue().to_pybytes())
    headers = {"content-disposition": f"attachment; filename={route_id}.parquet"}
    return StreamingResponse(buffer, media_type="application/x-parquet", headers=headers)


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
