from __future__ import annotations

import io
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence, cast
from urllib.parse import parse_qsl, urlencode, urlsplit

import duckdb
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__ as PACKAGE_VERSION
from ..config import Config
from ..static.chartjs import CHARTJS_VERSION
from ..core.routes import ParameterSpec, ParameterType, RouteDefinition
from ..plugins.charts import render_route_charts
from .analytics import AnalyticsStore, ExecutionMetrics
from .auth import resolve_auth_adapter
from .cache import CacheStore, parse_invariant_filters
from .csv import append_record
from .email import load_email_sender
from .execution import RouteExecutionError, RouteExecutor
from .meta import MetaStore, _utcnow
from .overlay import (
    OverlayStore,
    apply_overrides,
    compute_row_key_from_values,
)
from .postprocess import (
    build_chartjs_configs,
    render_cards_html_with_assets,
    render_chartjs_html,
    render_feed_html,
    render_table_html,
    table_to_records,
)
from .preprocess import run_preprocessors
from .session import SESSION_COOKIE_NAME, SessionStore
from .share import CreatedShare, ShareStore
from .vendor import CHARTJS_FILENAME, DEFAULT_CHARTJS_SOURCE, ensure_chartjs_vendor


@dataclass(slots=True)
class RouteExecutionResult:
    """Container for executed route artifacts."""

    params: Mapping[str, object]
    table: pa.Table
    elapsed_ms: float
    total_rows: int
    offset: int
    limit: int | None
    meta: Mapping[str, object] | None


@dataclass(slots=True, frozen=True)
class ParsedLocalReference:
    """Structured result returned by :func:`_parse_local_reference`."""

    route_id: str
    params: Mapping[str, str]
    columns: tuple[str, ...]
    format: str | None
    limit: str | None
    offset: str | None


@dataclass(slots=True)
class LocalReferenceRequest:
    """Parsed payload for ``/local/resolve`` requests."""

    route: RouteDefinition
    params: Mapping[str, object]
    columns: list[str]
    format: str
    limit: int | None
    offset: int | None
    redacted_columns: list[str] | None
    record_analytics: bool


_ERROR_TAXONOMY = {
    "missing_parameter": {
        "message": "A required parameter was not provided.",
        "hint": "Ensure the query string includes the documented parameter name.",
        "category": "ValidationError",
        "status": 400,
    },
    "invalid_parameter": {
        "message": "A parameter value could not be converted to the expected type.",
        "hint": "Verify the value is formatted as documented (e.g. integer, boolean).",
        "category": "ValidationError",
        "status": 400,
    },
    "unknown_parameter": {
        "message": "The query referenced an undefined parameter.",
        "hint": "Recompile routes or check the metadata for available parameters.",
        "category": "ValidationError",
        "status": 400,
    },
}


def _prepare_chartjs_assets(app: FastAPI, storage_root: Path) -> None:
    """Populate Chart.js vendor state on ``app.state``."""

    vendor_result = ensure_chartjs_vendor(storage_root)
    chartjs_path = Path(storage_root) / "static" / "vendor" / "chartjs" / CHARTJS_FILENAME
    app.state.chartjs_asset_path = chartjs_path
    app.state.chartjs_vendor_error = vendor_result.error
    if vendor_result.prepared and chartjs_path.exists():
        app.state.chartjs_script_url = f"/vendor/{CHARTJS_FILENAME}?v={CHARTJS_VERSION}"
    else:
        app.state.chartjs_script_url = DEFAULT_CHARTJS_SOURCE


def create_app(routes: Sequence[RouteDefinition], config: Config) -> FastAPI:
    if not routes:
        raise ValueError("At least one route must be provided to create the application")

    app = FastAPI(title="webbed_duck", version=PACKAGE_VERSION)
    app.state.config = config
    app.state.analytics = AnalyticsStore(
        weight=config.analytics.weight_interactions,
        enabled=config.analytics.enabled,
    )
    app.state.routes = list(routes)
    app.state.route_index = {route.id: route for route in app.state.routes}
    app.state.overlays = OverlayStore(config.server.storage_root)
    app.state.meta = MetaStore(config.server.storage_root)
    app.state.session_store = SessionStore(app.state.meta, config.auth)
    app.state.share_store = ShareStore(app.state.meta, config)
    app.state.email_sender = load_email_sender(config.email.adapter)
    app.state.auth_adapter = resolve_auth_adapter(
        config.auth.mode,
        config=config,
        session_store=app.state.session_store,
    )

    app.state.cache_store = CacheStore(config.server.storage_root)
    chartjs_route = f"/vendor/{CHARTJS_FILENAME}"
    _prepare_chartjs_assets(app, config.server.storage_root)
    app.state._dynamic_route_handles = _register_dynamic_routes(app, app.state.routes)

    assets_root = Path(__file__).resolve().parent.parent / "static" / "assets" / "wd"
    static_files = StaticFiles(
        directory=str(assets_root) if assets_root.exists() else None,
        packages=[("webbed_duck.static", "assets/wd")],
        html=False,
        check_dir=False,
    )
    app.mount("/assets/wd", static_files, name="wd-assets")

    @app.get(chartjs_route)
    async def serve_chartjs_asset() -> FileResponse:
        path = app.state.chartjs_asset_path
        if not path.exists():
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "not_found",
                    "message": "Chart.js asset has not been prepared",
                },
            )
        return FileResponse(path, media_type="application/javascript")

    def _reload_routes(new_routes: Sequence[RouteDefinition]) -> None:
        _replace_dynamic_routes(app, list(new_routes))

    app.state.reload_routes = _reload_routes

    if config.auth.mode == "pseudo":
        @app.post("/auth/pseudo/session")
        async def create_pseudo_session(request: Request) -> Mapping[str, object]:
            payload = _require_json_mapping(
                await request.json(), message="Session payload must be an object"
            )
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
        display_folder, routes_payload, folders_payload = _build_folder_listing(
            app.state.routes, stats, folder
        )
        return {"folder": display_folder, "routes": routes_payload, "folders": folders_payload}

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
        payload = _require_json_mapping(
            await request.json(), message="Override payload must be an object"
        )
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
        payload = _require_json_mapping(
            await request.json(), message="Append payload must be an object"
        )
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
        payload = _require_json_mapping(
            await request.json(), message="Share payload must be an object"
        )
        default_fmt = route.default_format or "html_t"
        fmt_raw = payload.get("format")
        fmt = fmt_raw.lower() if isinstance(fmt_raw, str) else default_fmt.lower()
        fmt = _validate_format(fmt, route)
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
        columns = _coerce_sequence(payload.get("columns"))
        max_rows_value = payload.get("max_rows")
        share_limit: int | None
        if max_rows_value is None:
            share_limit = 200
        else:
            try:
                share_limit = int(max_rows_value)
            except (TypeError, ValueError) as exc:
                raise _http_error("invalid_parameter", "max_rows must be an integer") from exc
            if share_limit <= 0:
                share_limit = None
        redacted_columns = _resolve_share_redaction(route, payload)
        share = app.state.share_store.create(
            route.id,
            params=params,
            fmt=fmt,
            redact_columns=redacted_columns,
            created_by_hash=user.email_hash,
            request=request,
        )
        share_url = str(request.url_for("resolve_share", token=share.token))
        inline_html, attachments_payload, artifact_meta = _build_share_artifacts(
            route,
            request,
            params,
            columns,
            share_limit,
            payload,
            share,
            app.state.config,
            redacted_columns,
        )
        if app.state.email_sender is not None:
            subject = f"{route.title or route.id} shared with you"
            html_body, text_body = _render_share_email(
                route,
                share_url,
                share.expires_at,
                user,
                inline_html,
                bool(attachments_payload),
            )
            try:
                app.state.email_sender(
                    recipients,
                    subject,
                    html_body,
                    text_body,
                    attachments_payload or None,
                )
            except Exception as exc:  # pragma: no cover - adapter errors vary
                raise HTTPException(status_code=502, detail={"code": "email_failed", "message": str(exc)}) from exc
        return {
            "share": {
                "token": share.token,
                "expires_at": share.expires_at.isoformat(),
                "url": share_url,
                "format": fmt,
                "attachments": artifact_meta["attachments"],
                "inline_snapshot": bool(inline_html),
                "rows_shared": artifact_meta["rows"],
                "redacted_columns": artifact_meta["redacted_columns"],
                "watermark": artifact_meta["watermark_applied"],
                "zipped": artifact_meta["zipped"],
                "zip_encrypted": artifact_meta["zip_encrypted"],
                "total_rows": artifact_meta["total_rows"],
            }
        }

    @app.get("/shares/{token}", name="resolve_share")
    async def resolve_share(token: str, request: Request) -> Response:
        record = app.state.share_store.resolve(token, request)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "share_not_found", "message": "Share link is invalid or expired"})
        route = _get_route(app.state.routes, record.route_id)
        fmt_override = request.query_params.get("format")
        fmt_value = fmt_override.lower() if fmt_override else record.format.lower()
        fmt = _validate_format(fmt_value, route)
        limit = _parse_optional_int(request.query_params.get("limit"))
        offset = _parse_optional_int(request.query_params.get("offset"))
        columns = request.query_params.getlist("column")
        return _render_route_response(
            route,
            request,
            record.params,
            fmt,
            limit,
            offset,
            columns,
            redacted_columns=record.redact_columns,
            record_analytics=False,
        )

    @app.post("/local/resolve")
    async def resolve_local_reference(request: Request) -> Response:
        try:
            payload = await request.json()
        except ValueError as exc:  # pragma: no cover - FastAPI normalizes to ValueError
            raise _http_error("invalid_parameter", "Request body must be a JSON object") from exc
        if not isinstance(payload, Mapping):
            raise _http_error("invalid_parameter", "Request body must be a JSON object")

        parsed = _build_local_reference_request(payload, app.state.routes)

        return _render_route_response(
            parsed.route,
            request,
            parsed.params,
            parsed.format,
            parsed.limit,
            parsed.offset,
            parsed.columns,
            parsed.redacted_columns,
            record_analytics=parsed.record_analytics,
        )

    return app


_REFERENCE_KEYS = ("reference", "ref", "target", "route")


def _resolve_reference_alias(payload: Mapping[str, object]) -> str:
    for key in _REFERENCE_KEYS:
        if key not in payload:
            continue
        value = payload[key]
        if value is None:
            continue
        if not isinstance(value, str):
            raise TypeError(f"{key} must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{key} must be a non-empty string")
        return stripped
    raise KeyError("reference")


def _build_local_reference_request(
    payload: Mapping[str, object], routes: Sequence[RouteDefinition]
) -> LocalReferenceRequest:
    try:
        reference = _resolve_reference_alias(payload)
    except KeyError as exc:
        raise _http_error("missing_parameter", "reference is required") from exc
    except (TypeError, ValueError) as exc:
        raise _http_error("invalid_parameter", str(exc)) from exc

    try:
        parsed = _parse_local_reference(reference)
    except ValueError as exc:
        raise _http_error("invalid_parameter", str(exc)) from exc

    route = _get_route(routes, parsed.route_id)

    raw_params: dict[str, object] = dict(parsed.params)
    if "params" in payload:
        params_override = payload["params"]
        if params_override is None:
            params_override = {}
        if not isinstance(params_override, Mapping):
            raise _http_error("invalid_parameter", "params must be an object")
        for key, value in params_override.items():
            raw_params[str(key)] = value
    try:
        params = _prepare_share_params(route, raw_params)
    except ValueError as exc:
        message = str(exc).replace("for share", "for local reference")
        raise _http_error("invalid_parameter", message) from exc

    columns = list(parsed.columns)
    if "columns" in payload:
        columns = _normalize_columns(payload["columns"])

    limit = _parse_optional_int(parsed.limit) if parsed.limit is not None else None
    offset = _parse_optional_int(parsed.offset) if parsed.offset is not None else None
    if "limit" in payload:
        limit = _coerce_int(payload["limit"], "limit")
    if "offset" in payload:
        offset = _coerce_int(payload["offset"], "offset")

    fmt = parsed.format or route.default_format or "json"
    if "format" in payload:
        fmt_value = payload["format"]
        if fmt_value is None:
            fmt = route.default_format or "json"
        elif isinstance(fmt_value, str):
            fmt = fmt_value
        else:
            raise _http_error("invalid_parameter", "format must be a string")

    redacted_columns = None
    if "redact_columns" in payload and payload["redact_columns"] is not None:
        redacted_columns = _normalize_columns(payload["redact_columns"])

    return LocalReferenceRequest(
        route=route,
        params=params,
        columns=columns,
        format=fmt,
        limit=limit,
        offset=offset,
        redacted_columns=redacted_columns,
        record_analytics=bool(payload.get("record_analytics", False)),
    )


def _make_endpoint(route: RouteDefinition):
    async def endpoint(request: Request) -> Response:
        params = _collect_params(route, request)
        limit = _parse_optional_int(request.query_params.get("limit"))
        offset = _parse_optional_int(request.query_params.get("offset"))
        columns = request.query_params.getlist("column")
        raw_format = request.query_params.get("format")
        if raw_format:
            fmt = raw_format.lower()
        else:
            fmt = (route.default_format or "json").lower()

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
    redacted_columns: Sequence[str] | None = None,
    *,
    record_analytics: bool,
) -> Response:
    fmt = _validate_format(fmt, route)
    drop_set = {str(name) for name in redacted_columns} if redacted_columns else set()
    filtered_columns = [col for col in columns if col not in drop_set] if drop_set else columns
    result = _execute_route(route, request, params, filtered_columns, offset, limit)
    if drop_set:
        table, _ = _apply_column_redaction(result.table, drop_set)
        result = RouteExecutionResult(
            params=result.params,
            table=table,
            elapsed_ms=result.elapsed_ms,
            total_rows=result.total_rows,
            offset=result.offset,
            limit=result.limit,
            meta=result.meta,
        )

    metadata = route.metadata if isinstance(route.metadata, Mapping) else {}
    charts_source = metadata.get("charts") if isinstance(metadata.get("charts"), Sequence) else []
    if route.charts:
        charts_source = route.charts
    charts_meta = render_route_charts(result.table, charts_source)

    if record_analytics:
        _record_route_execution(request.app.state, route, result)

    return _format_response(
        result,
        fmt,
        route,
        request,
        charts_meta,
        charts_source,
        watermark=None,
    )


def _record_route_execution(state: Any, route: RouteDefinition, result: RouteExecutionResult) -> None:
    analytics = getattr(state, "analytics", None)
    config = getattr(state, "config", None)
    overlays = getattr(state, "overlays", None)
    if analytics is None or config is None or overlays is None:
        return
    if not getattr(getattr(config, "analytics", None), "enabled", True):
        return
    interactions = overlays.count_for_route(route.id)
    analytics.record_execution(
        route.id,
        ExecutionMetrics.from_execution_result(
            result,
            interactions=interactions,
        ),
    )


def _validate_format(fmt: str, route: RouteDefinition | None = None) -> str:
    allowed = {
        "json",
        "table",
        "html_t",
        "html_c",
        "feed",
        "chart_js",
        "arrow",
        "arrow_rpc",
        "csv",
        "parquet",
    }
    fmt = fmt.lower()
    if fmt not in allowed:
        raise _http_error("invalid_parameter", f"Unsupported format '{fmt}'")
    if route and route.allowed_formats:
        route_allowed = {item.lower() for item in route.allowed_formats}
        if fmt not in route_allowed:
            raise _http_error("invalid_parameter", f"Format '{fmt}' not enabled for route '{route.id}'")
    return fmt


def _select_columns(table: pa.Table, columns: Sequence[str]) -> pa.Table:
    if not columns:
        return table
    selectable = [col for col in columns if col in table.column_names]
    if not selectable:
        return table
    return table.select(selectable)


def _execute_route(
    route: RouteDefinition,
    request: Request,
    params: Mapping[str, object],
    columns: Sequence[str],
    offset: int | None,
    limit: int | None,
) -> RouteExecutionResult:
    processed = run_preprocessors(route.preprocess, params, route=route, request=request)
    ordered = [_value_for_name(processed, name, route) for name in route.param_order]
    sanitized_offset = max(0, offset or 0)
    sanitized_limit = None if limit is None else max(0, int(limit))
    cache_store: CacheStore | None = getattr(request.app.state, "cache_store", None)
    executor = RouteExecutor(
        getattr(request.app.state, "route_index", {}),
        cache_store=cache_store,
        config=request.app.state.config,
    )
    start = time.perf_counter()
    try:
        cache_result = executor.execute_relation(
            route,
            processed,
            ordered=ordered,
            preprocessed=True,
            offset=sanitized_offset,
            limit=sanitized_limit,
        )
    except duckdb.Error as exc:  # pragma: no cover - safety net
        raise HTTPException(status_code=500, detail={"code": "duckdb_error", "message": str(exc)}) from exc
    except RouteExecutionError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "route_execution_error", "message": str(exc)},
        ) from exc
    except RuntimeError as exc:  # pragma: no cover - cache safeguards
        raise HTTPException(status_code=500, detail={"code": "cache_error", "message": str(exc)}) from exc

    metadata = route.metadata if isinstance(route.metadata, Mapping) else {}
    table = apply_overrides(cache_result.table, metadata, request.app.state.overlays.list_for_route(route.id))
    table = _select_columns(table, columns)
    elapsed_ms = (time.perf_counter() - start) * 1000
    applied_limit = cache_result.applied_limit
    if sanitized_limit is not None and applied_limit is None:
        applied_limit = sanitized_limit
    return RouteExecutionResult(
        params=processed,
        table=table,
        elapsed_ms=elapsed_ms,
        total_rows=cache_result.total_rows,
        offset=cache_result.applied_offset,
        limit=applied_limit,
        meta=cache_result.meta,
    )


def _format_response(
    result: RouteExecutionResult,
    fmt: str,
    route: RouteDefinition,
    request: Request,
    charts_meta: Sequence[Mapping[str, object]],
    chart_specs: Sequence[Mapping[str, object]],
    *,
    watermark: str | None,
) -> Response:
    metadata = route.metadata if isinstance(route.metadata, Mapping) else {}
    table = result.table
    pagination_values = {
        "offset": result.offset,
        "limit": result.limit,
    }
    if fmt in {"json", "table"}:
        records = table_to_records(table)
        payload = {
            "route_id": route.id,
            "title": route.title,
            "description": route.description,
            "row_count": len(records),
            "columns": table.column_names,
            "rows": records,
            "elapsed_ms": round(result.elapsed_ms, 3),
            "charts": charts_meta,
            "total_rows": result.total_rows,
            "offset": result.offset,
            "limit": result.limit,
        }
        return JSONResponse(payload)
    if fmt == "html_t":
        post_opts = route.postprocess.get("html_t") if isinstance(route.postprocess, Mapping) else None
        rpc_payload = _build_rpc_payload(request, fmt, result, table.num_rows)
        html = render_table_html(
            table,
            metadata,
            request.app.state.config,
            charts_meta,
            postprocess=post_opts,
            watermark=watermark,
            params=route.params,
            param_values=result.params,
            format_hint=fmt,
            pagination=pagination_values,
            rpc_payload=rpc_payload,
            cache_meta=result.meta,
        )
        response = HTMLResponse(html)
        _attach_rpc_headers(response, result)
        if rpc_payload.get("endpoint"):
            _add_vary_header(response.headers, "Accept")
            response.headers["Link"] = f"<{rpc_payload['endpoint']}>; rel=\"data\""
        return response
    if fmt == "html_c":
        post_opts = route.postprocess.get("html_c") if isinstance(route.postprocess, Mapping) else None
        rpc_payload = _build_rpc_payload(request, fmt, result, table.num_rows)
        html = render_cards_html_with_assets(
            table,
            metadata,
            request.app.state.config,
            charts=charts_meta,
            postprocess=post_opts,
            assets=route.assets,
            route_id=route.id,
            watermark=watermark,
            params=route.params,
            param_values=result.params,
            format_hint=fmt,
            pagination=pagination_values,
            rpc_payload=rpc_payload,
            cache_meta=result.meta,
        )
        response = HTMLResponse(html)
        _attach_rpc_headers(response, result)
        if rpc_payload.get("endpoint"):
            _add_vary_header(response.headers, "Accept")
            response.headers["Link"] = f"<{rpc_payload['endpoint']}>; rel=\"data\""
        return response
    if fmt == "feed":
        post_opts = route.postprocess.get("feed") if isinstance(route.postprocess, Mapping) else None
        html = render_feed_html(
            table,
            metadata,
            request.app.state.config,
            postprocess=post_opts,
        )
        return HTMLResponse(html)
    if fmt == "chart_js":
        post_opts = route.postprocess.get("chart_js") if isinstance(route.postprocess, Mapping) else None
        chart_configs = build_chartjs_configs(table, chart_specs)
        embed_value = request.query_params.get("embed")
        embed = False
        if embed_value is not None:
            embed = str(embed_value).lower() in {"1", "true", "yes"}
        html = render_chartjs_html(
            chart_configs,
            config=request.app.state.config,
            route_id=route.id,
            route_title=route.title,
            route_metadata=metadata,
            postprocess=post_opts,
            default_script_url=request.app.state.chartjs_script_url,
            embed=embed,
        )
        response = HTMLResponse(html)
        _attach_rpc_headers(response, result)
        return response
    if fmt == "arrow":
        return _arrow_stream_response(table)
    if fmt == "arrow_rpc":
        response = _arrow_stream_response(table)
        _attach_rpc_headers(response, result)
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


def _build_rpc_payload(
    request: Request,
    fmt: str,
    result: RouteExecutionResult,
    page_rows: int,
) -> dict[str, object]:
    params = dict(request.query_params.items())
    rpc_params = {key: value for key, value in params.items() if key != "format"}
    rpc_params["format"] = "arrow_rpc"
    if result.limit is not None:
        rpc_params["limit"] = str(result.limit)
    else:
        rpc_params.pop("limit", None)
    if result.offset:
        rpc_params["offset"] = str(result.offset)
    else:
        rpc_params.pop("offset", None)
    rpc_url = str(request.url.replace(query=urlencode(rpc_params)))

    html_params = params.copy()
    html_params["format"] = fmt
    if result.limit is not None:
        html_params["limit"] = str(result.limit)
    else:
        html_params.pop("limit", None)
    if result.offset:
        html_params["offset"] = str(result.offset)
    else:
        html_params.pop("offset", None)

    payload: dict[str, object] = {
        "endpoint": rpc_url,
        "format": "arrow_rpc",
        "total_rows": result.total_rows,
        "offset": result.offset,
        "limit": result.limit,
        "page_rows": page_rows,
    }
    if result.limit is not None:
        next_offset = (result.offset or 0) + page_rows
        if next_offset < result.total_rows:
            html_params_next = html_params.copy()
            html_params_next["offset"] = str(next_offset)
            next_href = str(request.url.replace(query=urlencode(html_params_next)))
            payload["next_href"] = next_href
            payload["next_offset"] = next_offset
    return payload


def _attach_rpc_headers(response: Response, result: RouteExecutionResult) -> None:
    response.headers["x-total-rows"] = str(result.total_rows)
    response.headers["x-offset"] = str(result.offset)
    limit_value = (
        result.limit if result.limit is not None else result.total_rows
    )
    response.headers["x-limit"] = str(limit_value)


def _add_vary_header(headers: MutableMapping[str, str], value: str) -> None:
    existing = headers.get("Vary")
    if existing:
        tokens = [item.strip() for item in existing.split(",") if item.strip()]
        if value in tokens:
            return
        tokens.append(value)
        headers["Vary"] = ", ".join(tokens)
    else:
        headers["Vary"] = value


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


def _table_to_csv_bytes(table: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    pacsv.write_csv(table, sink)
    return sink.getvalue().to_pybytes()


def _table_to_parquet_bytes(table: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink)
    return sink.getvalue().to_pybytes()


def _resolve_share_redaction(route: RouteDefinition, payload: Mapping[str, object]) -> list[str]:
    metadata = route.metadata if isinstance(route.metadata, Mapping) else {}
    share_meta = metadata.get("share") if isinstance(metadata, Mapping) else None
    drop_columns = {str(item) for item in _coerce_sequence(payload.get("redact_columns")) if str(item)}
    redact_pii_pref = payload.get("redact_pii")
    redact_pii_enabled = True if redact_pii_pref is None else bool(redact_pii_pref)
    if redact_pii_enabled and isinstance(share_meta, Mapping):
        drop_columns.update(str(item) for item in _coerce_sequence(share_meta.get("pii_columns")))
    return sorted(drop_columns)


def _apply_column_redaction(table: pa.Table, redacted_columns: Sequence[str]) -> tuple[pa.Table, list[str]]:
    if not redacted_columns:
        return table, []
    drop_set = {str(name) for name in redacted_columns}
    present = [name for name in table.column_names if name in drop_set]
    if not present:
        return table, []
    keep = [name for name in table.column_names if name not in drop_set]
    if not keep:
        raise _http_error("invalid_parameter", "Redaction removed all result columns")
    return table.select(keep), sorted(present)


def _enforce_share_size(total_bytes: int, max_bytes: int) -> None:
    if total_bytes > max_bytes:
        raise _http_error("invalid_parameter", "Attachments exceed configured share size limit")


def _zip_attachments(
    route_id: str, attachments: Sequence[tuple[str, bytes]], passphrase: object
) -> tuple[str, bytes, bool]:
    buffer = io.BytesIO()
    zip_name = f"{route_id}.zip"
    zip_encrypted = False

    try:  # pragma: no branch - small helper
        import pyzipper  # type: ignore
    except ModuleNotFoundError:  # pragma: no cover - exercised in tests via monkeypatch
        if passphrase:
            raise _http_error(
                "invalid_parameter",
                "Encrypted ZIP attachments require the optional 'pyzipper' dependency. "
                "Install it with 'pip install pyzipper' before requesting a passphrase.",
            )
        import zipfile

        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for filename, content in attachments:
                zf.writestr(filename, content)
        return zip_name, buffer.getvalue(), zip_encrypted

    with pyzipper.AESZipFile(
        buffer,
        "w",
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as zf:
        if passphrase:
            zf.setpassword(str(passphrase).encode("utf-8"))
            zip_encrypted = True
        for filename, content in attachments:
            zf.writestr(filename, content)
    return zip_name, buffer.getvalue(), zip_encrypted


def _build_share_artifacts(
    route: RouteDefinition,
    request: Request,
    params: Mapping[str, object],
    columns: Sequence[str],
    limit: int | None,
    payload: Mapping[str, object],
    share: CreatedShare,
    config: Config,
    redacted_columns: Sequence[str],
) -> tuple[str | None, list[tuple[str, bytes]], Mapping[str, object]]:
    metadata = route.metadata if isinstance(route.metadata, Mapping) else {}

    result = _execute_route(route, request, params, columns, offset=0, limit=limit)
    table = result.table

    table, removed_columns = _apply_column_redaction(table, redacted_columns)

    charts_source = metadata.get("charts") if isinstance(metadata.get("charts"), Sequence) else []
    if route.charts:
        charts_source = route.charts
    charts_meta = render_route_charts(table, charts_source)

    watermark_pref = payload.get("watermark")
    if watermark_pref is None:
        watermark_enabled = bool(config.share.watermark)
    else:
        watermark_enabled = bool(watermark_pref)
    watermark_text = payload.get("watermark_text")
    if watermark_enabled:
        watermark_text = watermark_text or _default_share_watermark(route, share)
    else:
        watermark_text = None

    inline_snapshot = bool(payload.get("inline_snapshot", True))
    inline_html = None
    post_opts = route.postprocess.get("html_t") if isinstance(route.postprocess, Mapping) else None
    if inline_snapshot:
        inline_html = render_table_html(
            table,
            metadata,
            config,
            charts_meta,
            postprocess=post_opts,
            watermark=watermark_text,
            cache_meta=result.meta,
        )

    attachments: list[tuple[str, bytes]] = []
    attachment_formats = payload.get("attachments") or []
    for fmt_name in attachment_formats:
        fmt_key = str(fmt_name).lower()
        if fmt_key not in {"csv", "parquet", "html"}:
            raise _http_error("invalid_parameter", f"Unsupported attachment format '{fmt_name}'")
        if fmt_key == "csv":
            attachments.append((f"{route.id}.csv", _table_to_csv_bytes(table)))
        elif fmt_key == "parquet":
            attachments.append((f"{route.id}.parquet", _table_to_parquet_bytes(table)))
        elif fmt_key == "html":
            html_body = inline_html
            if html_body is None:
                html_body = render_table_html(
                    table,
                    metadata,
                    config,
                    charts_meta,
                    postprocess=post_opts,
                    watermark=watermark_text,
                    cache_meta=result.meta,
                )
            attachments.append((f"{route.id}.html", html_body.encode("utf-8")))

    max_bytes = max(1, int(config.share.max_total_size_mb)) * 1024 * 1024
    total_size = sum(len(content) for _, content in attachments)
    _enforce_share_size(total_size, max_bytes)

    zip_requested = payload.get("zip")
    if zip_requested is None:
        zip_requested = bool(config.share.zip_attachments)
    zipped = False
    zip_encrypted = False
    attachment_names = [name for name, _ in attachments]
    attachments_payload = attachments
    if attachments and zip_requested:
        zip_passphrase = payload.get("zip_passphrase")
        if config.share.zip_passphrase_required and not zip_passphrase:
            raise _http_error("missing_parameter", "zip_passphrase is required for attachments")
        zip_name, zip_bytes, zip_encrypted = _zip_attachments(route.id, attachments, zip_passphrase)
        _enforce_share_size(len(zip_bytes), max_bytes)
        attachments_payload = [(zip_name, zip_bytes)]
        attachment_names = [zip_name]
        zipped = True

    artifact_meta = {
        "attachments": attachment_names,
        "rows": table.num_rows,
        "redacted_columns": removed_columns,
        "watermark_applied": bool(watermark_text),
        "zipped": zipped,
        "zip_encrypted": zip_encrypted,
        "total_rows": result.total_rows,
    }

    return inline_html, attachments_payload, artifact_meta


def _default_share_watermark(route: RouteDefinition, share: CreatedShare) -> str:
    expires = share.expires_at.isoformat(timespec="minutes")
    return f"webbed_duck share · {route.id} · expires {expires}"


def _render_share_email(
    route: RouteDefinition,
    url: str,
    expires_at: datetime,
    user,
    inline_html: str | None,
    has_attachments: bool,
) -> tuple[str, str]:
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
    if has_attachments:
        html += "<p>Attachments are included with this email.</p>"
    if inline_html:
        html += "<hr/>" + inline_html
    text = f"{title} shared by {creator}. Access: {url} (expires {expires})."
    if has_attachments:
        text += " Attachments included."
    return html, text


def _collect_params(route: RouteDefinition, request: Request) -> Mapping[str, object]:
    values: dict[str, object] = {}
    query_params = request.query_params
    for spec in route.params:
        raw_values = query_params.getlist(spec.name)
        if not raw_values:
            if spec.default is not None:
                values[spec.name] = spec.default
            elif spec.required:
                raise _http_error("missing_parameter", f"Missing required parameter '{spec.name}'")
            else:
                values[spec.name] = None
            continue
        if len(raw_values) == 1:
            raw_value = raw_values[0]
            try:
                values[spec.name] = spec.convert(raw_value)
            except ValueError as exc:
                raise _http_error("invalid_parameter", str(exc)) from exc
            continue

        converted_values: list[object] = []
        try:
            for raw_value in raw_values:
                converted_values.append(spec.convert(raw_value))
        except ValueError as exc:
            raise _http_error("invalid_parameter", str(exc)) from exc
        values[spec.name] = converted_values

    metadata = route.metadata if isinstance(route.metadata, Mapping) else {}
    cache_block_raw = metadata.get("cache") if metadata else None
    cache_block = cache_block_raw if isinstance(cache_block_raw, Mapping) else None
    raw_invariants = cache_block.get("invariant_filters") if cache_block else None
    invariant_specs = parse_invariant_filters(raw_invariants)
    for setting in invariant_specs:
        if setting.param in values:
            continue
        raw_values = query_params.getlist(setting.param)
        extra = setting.extra if isinstance(setting.extra, Mapping) else {}
        default_value = extra.get("default")
        raw_type = extra.get("type")
        param_type: ParameterType | None = None
        if isinstance(raw_type, str):
            try:
                param_type = ParameterType.from_string(raw_type)
            except ValueError:
                param_type = None
        converter_spec: ParameterSpec | None = None
        if param_type is not None:
            converter_spec = ParameterSpec(name=setting.param, type=param_type)

        def convert_invariant(raw_value: str) -> object:
            if converter_spec is None:
                return raw_value
            return converter_spec.convert(raw_value)

        if not raw_values:
            if default_value is not None:
                values[setting.param] = default_value
            else:
                values[setting.param] = None
            continue
        if len(raw_values) == 1:
            try:
                values[setting.param] = convert_invariant(raw_values[0])
            except ValueError as exc:
                raise _http_error("invalid_parameter", str(exc)) from exc
            continue
        try:
            values[setting.param] = [convert_invariant(item) for item in raw_values]
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


def _parse_local_reference(reference: str) -> ParsedLocalReference:
    prefix = "local:"
    if not reference.startswith(prefix):
        raise ValueError("reference must start with 'local:'")
    raw_target = reference[len(prefix):].strip()
    if not raw_target:
        raise ValueError("reference must include a route identifier")
    parsed = urlsplit(raw_target)
    route_id_raw = parsed.path or parsed.netloc
    route_id = route_id_raw.lstrip("/")
    if not route_id:
        raise ValueError("reference must include a route identifier")
    params: dict[str, str] = {}
    columns: list[str] = []
    fmt: str | None = None
    limit: str | None = None
    offset: str | None = None
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key == "format":
            fmt = value
        elif key == "column":
            columns.append(value)
        elif key == "columns":
            if value:
                columns.extend(item.strip() for item in value.split(",") if item.strip())
        elif key == "limit":
            limit = value
        elif key == "offset":
            offset = value
        else:
            params[key] = value
    return ParsedLocalReference(
        route_id=route_id,
        params=params,
        columns=tuple(columns),
        format=fmt,
        limit=limit,
        offset=offset,
    )


def _normalize_columns(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item) for item in value]
    return [str(value)]


def _coerce_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return _parse_optional_int(value)
    raise _http_error("invalid_parameter", f"{label} must be an integer")


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


def _build_folder_listing(
    routes: Sequence[RouteDefinition],
    stats: Mapping[str, Mapping[str, object]],
    folder: str | None,
) -> tuple[str, list[Mapping[str, object]], list[dict[str, object]]]:
    prefix = folder or "/"
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    base_prefix = prefix.rstrip("/") or "/"
    normalized = "/" if base_prefix == "/" else base_prefix + "/"

    routes_payload: list[Mapping[str, object]] = []
    folder_metrics: dict[str, dict[str, float | int]] = {}

    for route in routes:
        path = route.path
        if base_prefix != "/":
            if path == base_prefix:
                relative = ""
            elif not path.startswith(normalized):
                continue
            else:
                relative = path[len(normalized):]
        else:
            if folder and not path.startswith(prefix):
                continue
            relative = path.lstrip("/")

        metrics_raw = stats.get(route.id, {})
        route_metrics = {
            "hits": int(metrics_raw.get("hits", 0)),
            "rows": int(metrics_raw.get("rows", 0)),
            "avg_latency_ms": float(metrics_raw.get("avg_latency_ms", 0.0)),
            "interactions": int(metrics_raw.get("interactions", 0)),
        }

        if relative and "/" in relative:
            child = relative.split("/", 1)[0]
            child_path = (normalized + child).rstrip("/")
            agg = folder_metrics.setdefault(
                child_path,
                {"hits": 0, "rows": 0, "total_latency_ms": 0.0, "interactions": 0, "routes": 0},
            )
            agg["hits"] += route_metrics["hits"]
            agg["rows"] += route_metrics["rows"]
            agg["total_latency_ms"] += route_metrics["avg_latency_ms"] * max(1, route_metrics["hits"])
            agg["interactions"] += route_metrics["interactions"]
            agg["routes"] += 1
            continue

        routes_payload.append(
            {
                "id": route.id,
                "path": route.path,
                "title": route.title,
                "description": route.description,
                "metrics": route_metrics,
            }
        )

    routes_payload.sort(
        key=lambda item: (
            -int(item["metrics"]["hits"]),
            -int(item["metrics"]["interactions"]),
            item["path"],
        )
    )

    folders_payload: list[dict[str, object]] = []
    for folder_path, agg in folder_metrics.items():
        hits = int(agg["hits"])
        total_latency = float(agg["total_latency_ms"])
        avg_latency = total_latency / hits if hits else 0.0
        folders_payload.append(
            {
                "path": folder_path or "/",
                "hits": hits,
                "rows": int(agg["rows"]),
                "avg_latency_ms": round(avg_latency, 3),
                "interactions": int(agg["interactions"]),
                "route_count": int(agg["routes"]),
            }
        )
    folders_payload.sort(key=lambda item: (-int(item["hits"]), item["path"]))

    display_folder = normalized if normalized != "/" else "/"
    if display_folder.endswith("/") and display_folder != "/":
        display_folder = display_folder.rstrip("/")

    return display_folder, routes_payload, folders_payload


def _get_route(routes: Sequence[RouteDefinition], route_id: str) -> RouteDefinition:
    for route in routes:
        if route.id == route_id:
            return route
    raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"Route '{route_id}' not found"})


def _require_json_mapping(payload: object, *, message: str) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise _http_error("invalid_parameter", message)
    return cast(Mapping[str, object], payload)


def _http_error(code: str, message: str) -> HTTPException:
    entry = _ERROR_TAXONOMY.get(code, {})
    detail = {"code": code, "message": message}
    hint = entry.get("hint")
    if hint:
        detail["hint"] = hint
    category = entry.get("category")
    if category:
        detail["category"] = category
    status = int(entry.get("status", 400))
    return HTTPException(status_code=status, detail=detail)


def _register_dynamic_routes(app: FastAPI, routes: Sequence[RouteDefinition]) -> list[object]:
    handles: list[object] = []
    for route in routes:
        app.add_api_route(
            route.path,
            endpoint=_make_endpoint(route),
            methods=list(route.methods),
            summary=route.title,
            description=route.description,
        )
        handles.append(app.router.routes[-1])
    return handles


def _replace_dynamic_routes(app: FastAPI, routes: Sequence[RouteDefinition]) -> None:
    existing: Sequence[object] = getattr(app.state, "_dynamic_route_handles", [])
    if existing:
        app.router.routes = [route for route in app.router.routes if route not in existing]
    app.state.routes = list(routes)
    app.state.route_index = {route.id: route for route in app.state.routes}
    app.state._dynamic_route_handles = _register_dynamic_routes(app, routes)


__all__ = ["create_app"]
