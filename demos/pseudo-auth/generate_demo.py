"""Generate the pseudo-auth walkthrough from real HTTP interactions."""
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
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx
import uvicorn

# Ensure the repository root is on sys.path so ``webbed_duck`` can be imported
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from webbed_duck.config import Config, load_config  # noqa: E402
from webbed_duck.core.compiler import compile_routes  # noqa: E402
from webbed_duck.core.routes import load_compiled_routes  # noqa: E402
from webbed_duck.server import preferred_uvicorn_http_implementation  # noqa: E402
from webbed_duck.server.app import create_app  # noqa: E402
from webbed_duck.server.session import SESSION_COOKIE_NAME  # noqa: E402


@dataclasses.dataclass(slots=True)
class HTTPExchange:
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


def _snapshot_meta(storage_root: Path) -> dict[str, list[dict[str, Any]]]:
    database = storage_root / "runtime" / "meta.sqlite3"
    result = {"sessions": [], "shares": []}
    if not database.exists():
        return result
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        sessions = conn.execute(
            "SELECT token_hash, email, expires_at FROM sessions ORDER BY id"
        ).fetchall()
        shares = conn.execute(
            "SELECT token_hash, route_id, expires_at FROM shares ORDER BY id"
        ).fetchall()
    result["sessions"] = [dict(row) for row in sessions]
    result["shares"] = [dict(row) for row in shares]
    return result


def _remove_hashed_record(storage_root: Path, table: str, token: str | None) -> bool:
    if not token:
        return False
    database = storage_root / "runtime" / "meta.sqlite3"
    if not database.exists():
        return False
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with sqlite3.connect(database) as conn:
        cursor = conn.execute(f"DELETE FROM {table} WHERE token_hash = ?", (token_hash,))
        conn.commit()
        return cursor.rowcount > 0


def _find_open_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _ensure_directories(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _configure_runtime(config: Config, storage_root: Path, build_dir: Path, host: str, port: int) -> None:
    config.server.storage_root = storage_root
    config.server.build_dir = build_dir
    config.server.source_dir = None
    config.server.auto_compile = False
    config.server.watch = False
    config.server.host = host
    config.server.port = port
    config.auth.mode = "pseudo"
    config.auth.allowed_domains = ["example.com"]
    config.email.adapter = None


def _write_markdown(
    path: Path,
    *,
    interactions: list[HTTPExchange],
    context: dict[str, Any],
    snapshots: list[tuple[str, dict[str, list[dict[str, Any]]]]],
) -> None:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    base_url = context["base_url"]
    runtime_dir = context["runtime_dir"]
    storage_root = context["storage_root"]
    lines: list[str] = []
    lines.append("# Pseudo Authentication & Share Demo")
    lines.append("")
    lines.append(f"_Generated automatically at {timestamp} UTC by running `python demos/pseudo-auth/generate_demo.py`._")
    lines.append("")
    lines.append(
        "> Pseudo authentication is intended for trusted intranets. Deploy behind a hardened proxy and external identity provider "
        "before exposing these endpoints to the public internet."
    )
    lines.append("")
    lines.append("## Environment setup")
    lines.append("")
    lines.append(f"* Base URL: `{base_url}`")
    lines.append(f"* Runtime directory: `{runtime_dir}`")
    lines.append(f"* Storage root: `{storage_root}`")
    lines.append(f"* Routes compiled from: `{context['source_dir']}` → `{context['build_dir']}`")
    lines.append("")
    lines.append("## HTTP interactions")
    lines.append("")
    for idx, exchange in enumerate(interactions, start=1):
        lines.append(f"### {idx}. {exchange.label}")
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
    if "share_meta" in context:
        lines.append("## Share metadata")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(context["share_meta"], indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")
    if "share_resolution" in context:
        lines.append("## Share resolution payload")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(context["share_resolution"], indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")
    if "local_resolve" in context:
        lines.append("## Local `/local/resolve` response")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(context["local_resolve"], indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")
    if snapshots:
        lines.append("## Meta store snapshots")
        lines.append("")
        for label, snapshot in snapshots:
            lines.append(f"### {label}")
            lines.append("")
            for table in ("sessions", "shares"):
                lines.append(f"**{table.title()} table**")
                lines.append("")
                rows = snapshot.get(table, [])
                if rows:
                    lines.append("```json")
                    lines.append(json.dumps(rows, indent=2, sort_keys=True))
                    lines.append("```")
                else:
                    lines.append("(empty)")
                lines.append("")
    if "cleanup" in context:
        lines.append("## Cleanup summary")
        lines.append("")
        lines.append(context["cleanup"])
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
    _ensure_directories(build_dir)
    _ensure_directories(storage_root)

    compile_routes(source_dir, build_dir)
    routes = load_compiled_routes(build_dir)

    config = load_config(None)
    _configure_runtime(config, storage_root, build_dir, host, port)

    app = create_app(routes, config)
    uvicorn_config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        http=preferred_uvicorn_http_implementation(),
    )
    server = uvicorn.Server(uvicorn_config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    start = time.time()
    while not getattr(server, "started", False):
        if not server_thread.is_alive():
            raise RuntimeError("Uvicorn server failed to start")
        if time.time() - start > 15:
            raise TimeoutError("Timed out waiting for the server to start")
        time.sleep(0.05)

    base_url = f"http://{host}:{port}"
    interactions: list[HTTPExchange] = []
    share_token: str | None = None
    session_token: str | None = None
    snapshots: list[tuple[str, dict[str, list[dict[str, Any]]]]] = []
    context: dict[str, Any] = {
        "base_url": base_url,
        "runtime_dir": str(runtime_dir.relative_to(REPO_ROOT)),
        "storage_root": str(storage_root.relative_to(REPO_ROOT)),
        "source_dir": str(source_dir.relative_to(REPO_ROOT)),
        "build_dir": str(build_dir.relative_to(REPO_ROOT)),
    }

    client = httpx.Client(base_url=base_url, headers={"User-Agent": "pseudo-auth-demo/1.0"}, timeout=30.0)
    try:
        login_response = client.post(
            "/auth/pseudo/session",
            json={"email": "analyst@example.com", "remember_me": True},
        )
        interactions.append(_capture_exchange("Create pseudo session", login_response))
        session_token = client.cookies.get(SESSION_COOKIE_NAME)

        inspect_response = client.get("/auth/pseudo/session")
        interactions.append(_capture_exchange("Inspect current session", inspect_response))

        share_payload = {
            "emails": ["teammate@example.com"],
            "format": "json",
            "params": {"name": "Pseudo Demo"},
        }
        share_response = client.post("/routes/hello_world/share", json=share_payload)
        interactions.append(_capture_exchange("Create share for hello_world", share_response))
        share_json = share_response.json()["share"]
        context["share_meta"] = share_json
        share_token = share_json["token"]

        resolve_response = client.get(f"/shares/{share_token}?format=json")
        interactions.append(_capture_exchange("Resolve share token", resolve_response))
        context["share_resolution"] = resolve_response.json()

        local_response = client.post(
            "/local/resolve",
            json={
                "reference": "local:hello_world?limit=1&column=greeting",
                "params": {"name": "Pseudo Demo"},
                "format": "json",
                "columns": ["greeting"],
                "record_analytics": False,
            },
        )
        interactions.append(_capture_exchange("Resolve route via /local/resolve", local_response))
        context["local_resolve"] = local_response.json()

        snapshots.append(("After share creation", _snapshot_meta(storage_root)))

        delete_response = client.delete("/auth/pseudo/session")
        interactions.append(_capture_exchange("Delete pseudo session", delete_response))

        snapshots.append(("After DELETE /auth/pseudo/session", _snapshot_meta(storage_root)))

    finally:
        client.close()
        server.should_exit = True
        server_thread.join(timeout=10)

    if server_thread.is_alive():
        raise RuntimeError("Server thread did not shut down cleanly")

    share_removed = _remove_hashed_record(storage_root, "shares", share_token)
    session_removed = _remove_hashed_record(storage_root, "sessions", session_token)
    snapshots.append(("After manual cleanup", _snapshot_meta(storage_root)))

    context["cleanup"] = (
        "Removed share and session rows from the SQLite meta store" if share_removed or session_removed else "No rows required manual cleanup"
    )

    demo_path = Path(__file__).with_name("demo.md")
    _write_markdown(demo_path, interactions=interactions, context=context, snapshots=snapshots)


if __name__ == "__main__":
    main()
