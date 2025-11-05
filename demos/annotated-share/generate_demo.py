"""Generate the annotated share demo transcript."""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import hashlib
import json
import socket
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterable

import httpx
import uvicorn

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from webbed_duck.config import Config, load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.local import LocalRouteRunner
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server import preferred_uvicorn_http_implementation
from webbed_duck.server.app import create_app
from webbed_duck.server.overlay import compute_row_key


ROUTE_ID = "hello_world"
DEMO_NAME = "Narrative Surprise"


@dataclasses.dataclass(slots=True)
class HTTPExchange:
    """Captured HTTP request/response pair."""

    label: str
    request_line: str
    request_headers: list[str]
    request_body: str | None
    response_line: str
    response_headers: list[str]
    response_body: str | None


def _format_headers(headers: Iterable[tuple[bytes, bytes]]) -> list[str]:
    formatted: list[str] = []
    for key, value in headers:
        formatted.append(f"{key.decode('latin-1')}: {value.decode('latin-1')}")
    return formatted


def _format_body(raw: bytes | None, content_type: str | None) -> str | None:
    if not raw:
        return None
    if content_type and "application/json" in content_type.lower():
        with contextlib.suppress(Exception):
            parsed = json.loads(raw)
            return json.dumps(parsed, indent=2, sort_keys=True)
    with contextlib.suppress(UnicodeDecodeError):
        return raw.decode()
    return raw.hex()


def _capture_exchange(label: str, response: httpx.Response) -> HTTPExchange:
    request = response.request
    url = request.url
    request_line = f"{request.method} {url.raw_path.decode()} HTTP/1.1"
    request_headers = _format_headers(request.headers.raw)
    request_body = _format_body(request.content, request.headers.get("content-type"))

    response_line = f"HTTP/1.1 {response.status_code} {response.reason_phrase}".strip()
    response_headers = _format_headers(response.headers.raw)
    response_body = _format_body(response.content, response.headers.get("content-type"))

    return HTTPExchange(
        label=label,
        request_line=request_line,
        request_headers=request_headers,
        request_body=request_body,
        response_line=response_line,
        response_headers=response_headers,
        response_body=response_body,
    )


def _find_open_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _ensure_directories(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def _configure_config(
    config: Config,
    *,
    storage_root: Path,
    build_dir: Path,
    host: str,
    port: int,
) -> list[tuple[str, str, str]]:
    toggles: list[tuple[str, str, str]] = []

    def _record(path: str, old: Any, new: Any) -> None:
        toggles.append((path, repr(old), repr(new)))

    _record("server.storage_root", config.server.storage_root, storage_root)
    config.server.storage_root = storage_root
    _record("server.build_dir", config.server.build_dir, build_dir)
    config.server.build_dir = build_dir
    _record("server.source_dir", config.server.source_dir, None)
    config.server.source_dir = None
    _record("server.auto_compile", config.server.auto_compile, False)
    config.server.auto_compile = False
    _record("server.watch", config.server.watch, False)
    config.server.watch = False
    _record("server.host", config.server.host, host)
    config.server.host = host
    _record("server.port", config.server.port, port)
    config.server.port = port

    _record("auth.mode", config.auth.mode, "pseudo")
    config.auth.mode = "pseudo"
    if not config.auth.allowed_domains:
        config.auth.allowed_domains = ["example.com"]

    _record("feature_flags.overrides_enabled", config.feature_flags.overrides_enabled, True)
    config.feature_flags.overrides_enabled = True

    _record("email.adapter", config.email.adapter, None)
    config.email.adapter = None
    _record(
        "email.bind_share_to_user_agent",
        config.email.bind_share_to_user_agent,
        True,
    )
    config.email.bind_share_to_user_agent = True
    _record("email.bind_share_to_ip_prefix", config.email.bind_share_to_ip_prefix, True)
    config.email.bind_share_to_ip_prefix = True

    return toggles


def _snapshot_meta(storage_root: Path) -> dict[str, list[dict[str, Any]]]:
    database = storage_root / "runtime" / "meta.sqlite3"
    result = {"shares": []}
    if not database.exists():
        return result
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT token_hash, route_id, format, expires_at FROM shares ORDER BY id"
        ).fetchall()
    result["shares"] = [dict(row) for row in rows]
    return result


def _remove_share(storage_root: Path, token: str | None) -> bool:
    if not token:
        return False
    database = storage_root / "runtime" / "meta.sqlite3"
    if not database.exists():
        return False
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with sqlite3.connect(database) as conn:
        cursor = conn.execute("DELETE FROM shares WHERE token_hash = ?", (token_hash,))
        conn.commit()
        return cursor.rowcount > 0


def _clear_overrides(storage_root: Path) -> bool:
    path = storage_root / "runtime" / "overrides.json"
    if not path.exists():
        return False
    try:
        path.write_text("{}\n", encoding="utf-8")
    except OSError:
        return False
    return True


def _write_markdown(
    path: Path,
    *,
    toggles: list[tuple[str, str, str]],
    local_before: list[dict[str, Any]],
    before_row_key: str,
    local_after: list[dict[str, Any]],
    interactions: list[HTTPExchange],
    share_resolution: dict[str, Any],
    share_meta: dict[str, Any],
    snapshots: list[tuple[str, dict[str, list[dict[str, Any]]]]],
    cleanup_notes: list[str],
) -> None:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    lines: list[str] = []
    lines.append("<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->")
    lines.append("# Annotated Share Workflow Demo")
    lines.append("")
    lines.append(f"Generated on {timestamp} UTC.")
    lines.append("")
    lines.append(
        "This walkthrough pairs pseudo-auth overrides with share redaction so teams "
        "can annotate a slice for themselves while sending a sanitized export."
    )
    lines.append("")
    lines.append("## Feature toggles applied during the run")
    lines.append("")
    for path_str, before, after in toggles:
        lines.append(f"- **{path_str}**: `{before}` → `{after}`")
    lines.append("")
    lines.append("## Local runner snapshot before overrides")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(local_before, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("Row key used for overrides:")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(before_row_key, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## HTTP interactions")
    lines.append("")
    for index, exchange in enumerate(interactions, start=1):
        lines.append(f"### {index}. {exchange.label}")
        lines.append("")
        lines.append("**Request**")
        lines.append("")
        lines.append("```http")
        lines.append(exchange.request_line)
        lines.extend(exchange.request_headers)
        if exchange.request_body:
            lines.append("")
            lines.append(exchange.request_body)
        lines.append("```")
        lines.append("")
        lines.append("**Response**")
        lines.append("")
        lines.append("```http")
        lines.append(exchange.response_line)
        lines.extend(exchange.response_headers)
        if exchange.response_body:
            lines.append("")
            lines.append(exchange.response_body)
        lines.append("```")
        lines.append("")
    lines.append("## Local runner snapshot after override")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(local_after, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Share metadata")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(share_meta, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Share resolution payload (redacted view)")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(share_resolution, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    if snapshots:
        lines.append("## Meta store snapshots")
        lines.append("")
        for label, snapshot in snapshots:
            lines.append(f"### {label}")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(snapshot, indent=2, sort_keys=True))
            lines.append("```")
            lines.append("")
    if cleanup_notes:
        lines.append("## Cleanup summary")
        lines.append("")
        for note in cleanup_notes:
            lines.append(f"- {note}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    host = "127.0.0.1"
    port = _find_open_port()
    demo_dir = Path(__file__).resolve().parent
    runtime_dir = demo_dir / "runtime"
    build_dir = runtime_dir / "build"
    storage_root = runtime_dir / "storage"
    source_dir = REPO_ROOT / "routes_src"

    _ensure_directories(build_dir, storage_root)

    compile_routes(source_dir, build_dir)
    routes = load_compiled_routes(build_dir)
    config = load_config(None)
    toggles = _configure_config(
        config,
        storage_root=storage_root,
        build_dir=build_dir,
        host=host,
        port=port,
    )

    runner = LocalRouteRunner(routes=routes, build_dir=build_dir, config=config)
    local_before = runner.run(
        ROUTE_ID,
        params={"name": DEMO_NAME},
        format="records",
    )
    if not isinstance(local_before, list) or not local_before:
        raise RuntimeError("Expected records from LocalRouteRunner")
    before_row_key = compute_row_key(
        local_before[0],
        ["greeting"],
        list(local_before[0].keys()),
    )

    app = create_app(routes, config)
    uvicorn_config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        http=preferred_uvicorn_http_implementation(),
    )
    server = uvicorn.Server(uvicorn_config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    start = time.time()
    while not getattr(server, "started", False):
        if not thread.is_alive():
            raise RuntimeError("Uvicorn server failed to start")
        if time.time() - start > 15:
            raise TimeoutError("Timed out waiting for server start")
        time.sleep(0.05)

    base_url = f"http://{host}:{port}"
    interactions: list[HTTPExchange] = []
    share_meta: dict[str, Any] | None = None
    share_resolution: dict[str, Any] | None = None
    share_token: str | None = None
    cleanup_notes: list[str] = []
    snapshots: list[tuple[str, dict[str, list[dict[str, Any]]]]] = []

    client = httpx.Client(base_url=base_url, timeout=30.0, headers={"User-Agent": "annotated-share-demo/1.0"})
    try:
        login_response = client.post(
            "/auth/pseudo/session",
            json={"email": "surprise@example.com", "remember_me": False},
        )
        interactions.append(_capture_exchange("Create pseudo session", login_response))

        override_payload = {
            "key": {"greeting": local_before[0]["greeting"]},
            "column": "note",
            "value": "Override note authored by generate_demo.py",
            "reason": "Annotating before sharing",
            "author": "annotated-share-demo@company.local",
        }
        override_response = client.post(
            f"/routes/{ROUTE_ID}/overrides",
            json=override_payload,
        )
        interactions.append(_capture_exchange("Apply override to note column", override_response))

        refreshed_response = client.get(
            "/hello",
            params={"format": "json", "name": DEMO_NAME},
        )
        interactions.append(_capture_exchange("Fetch JSON render with override", refreshed_response))

        share_payload = {
            "emails": ["teammate@example.com"],
            "format": "json",
            "params": {"name": DEMO_NAME},
            "redact_columns": ["note"],
            "record_analytics": False,
        }
        share_response = client.post(f"/routes/{ROUTE_ID}/share", json=share_payload)
        interactions.append(_capture_exchange("Create redacted share", share_response))
        share_meta = share_response.json()["share"]
        share_token = share_meta["token"]

        resolve_response = client.get(f"/shares/{share_token}?format=json")
        interactions.append(_capture_exchange("Resolve share token", resolve_response))
        share_resolution = resolve_response.json()

        overrides_list_response = client.get(f"/routes/{ROUTE_ID}/overrides")
        interactions.append(_capture_exchange("List overrides for route", overrides_list_response))

        logout_response = client.delete("/auth/pseudo/session")
        interactions.append(_capture_exchange("Delete pseudo session", logout_response))

        snapshots.append(("After HTTP flows", _snapshot_meta(storage_root)))
    finally:
        client.close()
        server.should_exit = True
        thread.join(timeout=10)

    if thread.is_alive():
        raise RuntimeError("Server thread did not shut down cleanly")

    local_after = runner.run(
        ROUTE_ID,
        params={"name": DEMO_NAME},
        format="records",
    )
    if not isinstance(local_after, list):
        raise RuntimeError("Expected records from LocalRouteRunner after override")

    share_removed = _remove_share(storage_root, share_token)
    overrides_cleared = _clear_overrides(storage_root)

    cleanup_notes.append(
        "Removed share row from meta store" if share_removed else "Share row already absent"
    )
    cleanup_notes.append(
        "Cleared overrides.json so reruns start fresh" if overrides_cleared else "overrides.json already empty"
    )

    if share_meta is None or share_resolution is None:
        raise RuntimeError("Share creation did not complete successfully")

    demo_path = Path(__file__).with_name("demo.md")
    _write_markdown(
        demo_path,
        toggles=toggles,
        local_before=local_before,
        before_row_key=before_row_key,
        local_after=local_after,
        interactions=interactions,
        share_resolution=share_resolution,
        share_meta=share_meta,
        snapshots=snapshots,
        cleanup_notes=cleanup_notes,
    )


if __name__ == "__main__":
    main()
