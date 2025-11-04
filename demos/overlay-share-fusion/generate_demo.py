"""Auto-generate the overlay/share fusion demo.

This scenario stitches together three capabilities that often get treated as
separate checkboxes:

* ``LocalRouteRunner`` for notebook-style previews without HTTP.
* Auto-generated parameter forms via ``/routes/{id}/schema``.
* Overlay notes blended into a pseudo-authenticated share workflow.

Run ``python demos/overlay-share-fusion/generate_demo.py`` from the repository
root. The script resets its working directory under ``demos/overlay-share-fusion``
(each execution wipes the previous run), captures HTTP transcripts, and renders a
Markdown walkthrough plus a machine-readable ``captures.json`` payload.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from webbed_duck.config import Config, load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.local import LocalRouteRunner
from webbed_duck.core.routes import RouteDefinition, load_compiled_routes
from webbed_duck.server.app import create_app
from webbed_duck.server.overlay import compute_row_key_from_values
from webbed_duck.server.session import SESSION_COOKIE_NAME


@dataclasses.dataclass(slots=True)
class HttpExchange:
    label: str
    request_line: str
    request_headers: list[str]
    request_body: str | None
    response_line: str
    response_headers: list[str]
    response_body: str | None


def _format_headers(headers: Mapping[str, str] | Any) -> list[str]:
    if hasattr(headers, "items"):
        items = headers.items()
    else:
        items = headers or []
    return [f"{key}: {value}" for key, value in sorted(items, key=lambda item: str(item[0]).lower())]


def _format_body(raw: bytes | str | None, content_type: str | None) -> str | None:
    if not raw:
        return None
    if isinstance(raw, str):
        return raw
    if content_type and "application/json" in content_type.lower():
        with contextlib.suppress(Exception):
            parsed = json.loads(raw)
            return json.dumps(parsed, indent=2, sort_keys=True)
    with contextlib.suppress(UnicodeDecodeError):
        return raw.decode()
    return raw.hex()


def _capture_exchange(label: str, response: Any) -> HttpExchange:
    prepared = response.request
    split = urlsplit(str(prepared.url))
    path = split.path or "/"
    if split.query:
        path = f"{path}?{split.query}"
    request_line = f"{prepared.method} {path} HTTP/1.1"
    request_headers = _format_headers(prepared.headers)
    body_source = getattr(prepared, "body", None)
    if body_source is None and hasattr(prepared, "content"):
        body_source = prepared.content
    request_body = _format_body(body_source, prepared.headers.get("content-type"))

    reason = getattr(response, "reason", None) or getattr(response, "reason_phrase", "")
    response_line = f"HTTP/1.1 {response.status_code} {reason}".strip()
    response_headers = _format_headers(response.headers)
    response_body = _format_body(response.content, response.headers.get("content-type"))

    return HttpExchange(
        label=label,
        request_line=request_line,
        request_headers=request_headers,
        request_body=request_body,
        response_line=response_line,
        response_headers=response_headers,
        response_body=response_body,
    )


def _ensure_runtime_dirs(root: Path) -> tuple[Path, Path]:
    if root.exists():
        shutil.rmtree(root)
    build_dir = root / "build"
    storage_root = root / "storage"
    build_dir.mkdir(parents=True, exist_ok=True)
    storage_root.mkdir(parents=True, exist_ok=True)
    return build_dir, storage_root


def _configure(config: Config, *, build_dir: Path, storage_root: Path) -> Config:
    config.server.storage_root = storage_root
    config.server.build_dir = build_dir
    config.server.source_dir = REPO_ROOT / "routes_src"
    config.auth.mode = "pseudo"
    config.feature_flags.overrides_enabled = True
    config.analytics.enabled = False
    config.email.bind_share_to_ip_prefix = False
    config.email.bind_share_to_user_agent = False
    config.share.zip_passphrase_required = False
    return config


def _resolve_hello(routes: list[RouteDefinition]) -> RouteDefinition:
    for route in routes:
        if route.id == "hello_world":
            return route
    raise RuntimeError("hello_world route was not compiled")


def _row_key(route: RouteDefinition, greeting_value: str) -> str:
    overrides_meta: Mapping[str, Any] | None = None
    if isinstance(route.metadata, Mapping):
        candidate = route.metadata.get("overrides")
        if isinstance(candidate, Mapping):
            overrides_meta = candidate
    key_columns = overrides_meta.get("key_columns") if overrides_meta else None
    return compute_row_key_from_values({"greeting": greeting_value}, key_columns)


def _write_markdown(
    path: Path,
    *,
    generated_at: str,
    runtime_dir: Path,
    local_before: Mapping[str, Any],
    local_after: Mapping[str, Any],
    exchanges: list[HttpExchange],
    form_json: Mapping[str, Any],
    share_payload: Mapping[str, Any],
    share_html_excerpt: str,
    cleanup_summary: str,
) -> None:
    lines: list[str] = []
    lines.append("<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->")
    lines.append("# Overlay + Share Fusion Demo")
    lines.append("")
    lines.append(f"Generated on {generated_at}.")
    lines.append("")
    lines.append(
        "This walkthrough starts with an offline LocalRouteRunner preview, then"
        " leans on the server's auto-generated parameter form to build a share"
        " that already includes a contextual overlay note."
    )
    lines.append("")
    lines.append("## Local preview before touching HTTP")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(local_before, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## HTTP interactions")
    lines.append("")
    for index, exchange in enumerate(exchanges, start=1):
        lines.append(f"### {index}. {exchange.label}")
        lines.append("")
        lines.append("**Request**")
        lines.append("")
        lines.append("```text")
        lines.append(exchange.request_line)
        for header in exchange.request_headers:
            lines.append(header)
        if exchange.request_body:
            lines.append("")
            lines.append(exchange.request_body)
        lines.append("```")
        lines.append("")
        lines.append("**Response**")
        lines.append("")
        lines.append("```text")
        lines.append(exchange.response_line)
        for header in exchange.response_headers:
            lines.append(header)
        if exchange.response_body:
            lines.append("")
            lines.append(exchange.response_body)
        lines.append("```")
        lines.append("")
    lines.append("## Auto-form payload from `/routes/{id}/schema`")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(form_json, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Local preview after the overlay")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(local_after, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Share metadata returned by the server")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(share_payload, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Share HTML excerpt")
    lines.append("")
    lines.append("```html")
    lines.append(share_html_excerpt)
    lines.append("```")
    lines.append("")
    lines.append("## Cleanup summary")
    lines.append("")
    lines.append(cleanup_summary)
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_captures(
    path: Path,
    *,
    generated_at: str,
    runtime_dir: Path,
    local_before: Mapping[str, Any],
    local_after: Mapping[str, Any],
    exchanges: list[HttpExchange],
    form_json: Mapping[str, Any],
    share_payload: Mapping[str, Any],
    share_html_excerpt: str,
    cleanup_summary: str,
) -> None:
    payload = {
        "generated_at": generated_at,
        "runtime_dir": str(runtime_dir.relative_to(REPO_ROOT)),
        "local": {
            "before_overlay": local_before,
            "after_overlay": local_after,
        },
        "http": [
            {
                "label": exchange.label,
                "request": {
                    "line": exchange.request_line,
                    "headers": exchange.request_headers,
                    "body": exchange.request_body,
                },
                "response": {
                    "line": exchange.response_line,
                    "headers": exchange.response_headers,
                    "body": exchange.response_body,
                },
            }
            for exchange in exchanges
        ],
        "form": form_json,
        "share": share_payload,
        "share_html_excerpt": share_html_excerpt,
        "cleanup": cleanup_summary,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _remove_hashed_record(database: Path, table: str, token: str | None) -> bool:
    if not token or not database.exists():
        return False
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with sqlite3.connect(database) as conn:
        cursor = conn.execute(f"DELETE FROM {table} WHERE token_hash = ?", (token_hash,))
        conn.commit()
        return cursor.rowcount > 0


def main() -> None:
    demo_dir = Path(__file__).resolve().parent
    runtime_dir = demo_dir / "runtime"
    build_dir, storage_root = _ensure_runtime_dirs(runtime_dir)

    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()

    compile_routes(REPO_ROOT / "routes_src", build_dir)
    routes = load_compiled_routes(build_dir)
    hello_route = _resolve_hello(routes)

    config = _configure(load_config(None), build_dir=build_dir, storage_root=storage_root)
    app = create_app(routes, config)

    runner = LocalRouteRunner(routes=routes, config=config)
    params = {"name": "Overlay Share Fusion"}

    local_before = runner.run("hello_world", params=params, format="records")

    exchanges: list[HttpExchange] = []
    share_payload_details: dict[str, Any] | None = None
    form_json: dict[str, Any] | None = None
    share_token: str | None = None
    session_token: str | None = None
    share_html_excerpt = ""

    override_value = "Notebook insight promoted to the share"
    override_reason = "Captured by overlay-share-fusion demo"
    overlay_author = "demo.generator@company.local"
    greeting_value = f"Hello, {params['name']}!"
    row_key = _row_key(hello_route, greeting_value)

    with TestClient(app) as client:
        client.headers.update({"User-Agent": "overlay-share-fusion/1.0"})
        login_response = client.post(
            "/auth/pseudo/session",
            json={"email": "analyst@example.com", "remember_me": True},
        )
        exchanges.append(_capture_exchange("Create pseudo session", login_response))
        session_token = client.cookies.get(SESSION_COOKIE_NAME)

        session_response = client.get("/auth/pseudo/session")
        exchanges.append(_capture_exchange("Inspect pseudo session", session_response))

        routes_response = client.get("/routes")
        exchanges.append(_capture_exchange("List available routes", routes_response))

        schema_response = client.get(f"/routes/{hello_route.id}/schema", params=params)
        exchanges.append(_capture_exchange("Fetch auto-generated form", schema_response))
        form_json = schema_response.json()

        html_response = client.get(
            hello_route.path,
            params={"format": "html_t", **params},
            headers={"accept": "text/html"},
        )
        exchanges.append(_capture_exchange("Render HTML before overlay", html_response))

        override_response = client.post(
            f"/routes/{hello_route.id}/overrides",
            json={
                "column": "note",
                "row_key": row_key,
                "value": override_value,
                "reason": override_reason,
                "author": overlay_author,
            },
        )
        exchanges.append(_capture_exchange("Submit overlay note", override_response))

        html_after_response = client.get(
            hello_route.path,
            params={"format": "html_t", **params},
            headers={"accept": "text/html"},
        )
        exchanges.append(_capture_exchange("Render HTML with overlay applied", html_after_response))

        share_payload = {
            "emails": ["teammate@example.com"],
            "format": "html_t",
            "params": params,
            "columns": ["greeting", "note", "created_at"],
            "max_rows": 5,
            "redact_columns": ["created_at"],
        }
        share_response = client.post(f"/routes/{hello_route.id}/share", json=share_payload)
        exchanges.append(_capture_exchange("Create share with overlay", share_response))
        share_body = share_response.json()
        share_section = share_body.get("share") or {}
        attachments_section = share_body.get("attachments") or {}
        artifact_section = share_body.get("artifact") or {}
        share_payload_details = {
            "share": share_section,
            "attachments": attachments_section,
            "artifact": artifact_section,
        }
        share_token = share_section.get("token") if isinstance(share_section, Mapping) else None

        share_html_response = client.get(
            f"/shares/{share_token}",
            params={"format": "html_t"},
            headers={"accept": "text/html"},
        )
        exchanges.append(_capture_exchange("Resolve share token", share_html_response))
        share_lines = share_html_response.text.strip().splitlines()
        share_html_excerpt = "\n".join(share_lines[:40])

    local_after = runner.run("hello_world", params=params, format="records")

    cleanup_messages: list[str] = []
    overlay_removed = app.state.overlays.remove(hello_route.id, row_key, "note")
    if overlay_removed:
        cleanup_messages.append("Removed overlay record from storage")
    meta_db = storage_root / "runtime" / "meta.sqlite3"
    if _remove_hashed_record(meta_db, "shares", share_token):
        cleanup_messages.append("Deleted share record from meta store")
    if _remove_hashed_record(meta_db, "sessions", session_token):
        cleanup_messages.append("Deleted session record from meta store")
    cleanup_summary = "\n".join(cleanup_messages) if cleanup_messages else "No state required manual cleanup"

    if form_json is None:
        form_json = {}
    if share_payload_details is None:
        share_payload_details = {}

    demo_path = demo_dir / "demo.md"
    _write_markdown(
        demo_path,
        generated_at=generated_at,
        runtime_dir=runtime_dir,
        local_before=local_before,
        local_after=local_after,
        exchanges=exchanges,
        form_json=form_json,
        share_payload=share_payload_details,
        share_html_excerpt=share_html_excerpt,
        cleanup_summary=cleanup_summary,
    )

    captures_path = demo_dir / "captures.json"
    _write_captures(
        captures_path,
        generated_at=generated_at,
        runtime_dir=runtime_dir,
        local_before=local_before,
        local_after=local_after,
        exchanges=exchanges,
        form_json=form_json,
        share_payload=share_payload_details,
        share_html_excerpt=share_html_excerpt,
        cleanup_summary=cleanup_summary,
    )


if __name__ == "__main__":
    main()
