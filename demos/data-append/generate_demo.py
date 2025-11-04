#!/usr/bin/env python3
"""Generate the data append demo transcript.

This script resets the CSV append storage, performs real append requests
against the compiled demo route, captures every interaction and filesystem
state, and regenerates ``demo.md`` from the live results. It restores the
original append storage contents on exit so reruns stay idempotent.
"""

from __future__ import annotations

import asyncio
import dataclasses
import datetime as _dt
import gc
import hashlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from webbed_duck.config import Config, load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import RouteDefinition, load_compiled_routes
from webbed_duck.server.app import create_app


DEMO_ROUTE_ID = "hello_world"


@dataclass(slots=True)
class DirectorySnapshot:
    """Structured representation of a directory tree."""

    exists: bool
    entries: list[Mapping[str, Any]]
    tree: str


def _ensure_path(value: Path | str | None, base: Path) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def _capture_directory(path: Path, *, relative_to: Path) -> DirectorySnapshot:
    try:
        relative_name = path.relative_to(relative_to)
    except ValueError:
        relative_name = Path(path.name)

    entries: list[Mapping[str, Any]] = []
    if not path.exists():
        tree = f"(absent: {relative_name.as_posix()})"
        return DirectorySnapshot(False, entries, tree)

    rel_root = relative_name.as_posix()
    entries.append({"type": "dir", "path": rel_root})

    for candidate in sorted(path.rglob("*")):
        rel = candidate.relative_to(relative_to).as_posix()
        if candidate.is_dir():
            entries.append({"type": "dir", "path": rel})
        else:
            stat = candidate.stat()
            entries.append(
                {
                    "type": "file",
                    "path": rel,
                    "size": stat.st_size,
                    "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
                }
            )

    tree = _render_tree(entries)
    return DirectorySnapshot(True, entries, tree)


def _render_tree(entries: Iterable[Mapping[str, Any]]) -> str:
    paths: dict[str, dict[str, Any] | None] = {}

    for entry in entries:
        path = entry.get("path")
        type_ = entry.get("type")
        if not path or not isinstance(path, str):
            continue
        segments = [segment for segment in path.split("/") if segment]
        if not segments:
            continue
        node = paths
        for segment in segments[:-1]:
            node = node.setdefault(segment, {})  # type: ignore[assignment]
        leaf = segments[-1]
        if type_ == "dir":
            node.setdefault(leaf, {})  # type: ignore[arg-type]
        else:
            node[leaf] = None  # type: ignore[index]

    if not paths:
        return "(empty)"

    def _emit(tree: Mapping[str, Any | None], prefix: str = "") -> list[str]:
        lines: list[str] = []
        items = sorted(tree.items())
        for index, (name, child) in enumerate(items):
            connector = "└── " if index == len(items) - 1 else "├── "
            lines.append(f"{prefix}{connector}{name}")
            if isinstance(child, Mapping):
                extension = "    " if index == len(items) - 1 else "│   "
                lines.extend(_emit(child, prefix + extension))
        return lines

    return "\n".join(_emit(paths))


@dataclass(slots=True)
class AppendStorageReset:
    """Context manager that resets and restores ``runtime/appends``."""

    storage_root: Path
    _backup_root: Path | None = dataclasses.field(default=None, init=False)
    _backup_path: Path | None = dataclasses.field(default=None, init=False)
    before: DirectorySnapshot | None = dataclasses.field(default=None, init=False)
    after_reset: DirectorySnapshot | None = dataclasses.field(default=None, init=False)
    _had_storage_root: bool = dataclasses.field(default=False, init=False)

    def __enter__(self) -> "AppendStorageReset":
        appends_dir = self.storage_root / "runtime" / "appends"
        self._had_storage_root = self.storage_root.exists()
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.before = _capture_directory(appends_dir, relative_to=self.storage_root)

        if appends_dir.exists():
            self._backup_root = Path(tempfile.mkdtemp(prefix="append-demo-"))
            self._backup_path = self._backup_root / "appends_backup"
            shutil.copytree(appends_dir, self._backup_path)
            shutil.rmtree(appends_dir)

        self.after_reset = _capture_directory(appends_dir, relative_to=self.storage_root)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        appends_dir = self.storage_root / "runtime" / "appends"
        if appends_dir.exists():
            shutil.rmtree(appends_dir)

        if self._backup_path and self._backup_path.exists():
            shutil.copytree(self._backup_path, appends_dir)
        else:
            runtime_dir = appends_dir.parent
            if runtime_dir.exists() and not any(runtime_dir.iterdir()):
                runtime_dir.rmdir()

        if self._backup_root and self._backup_root.exists():
            shutil.rmtree(self._backup_root)

        if not self._had_storage_root and self.storage_root.exists():
            shutil.rmtree(self.storage_root)


def _prepare_config(repo_root: Path, *, storage_override: Path | None = None) -> Config:
    config = load_config(None)
    storage_root = storage_override if storage_override is not None else repo_root / config.server.storage_root
    config.server.storage_root = storage_root.resolve()

    source_dir = _ensure_path(config.server.source_dir, repo_root)
    if source_dir is None:
        raise RuntimeError("server.source_dir must be configured for the demo")
    config.server.source_dir = source_dir

    build_dir = _ensure_path(config.server.build_dir, repo_root)
    if build_dir is None:
        raise RuntimeError("server.build_dir must be configured for the demo")
    config.server.build_dir = build_dir

    return config


def _select_route(routes: Iterable[RouteDefinition], route_id: str) -> RouteDefinition:
    for route in routes:
        if route.id == route_id:
            return route
    raise RuntimeError(f"Route {route_id!r} was not found in the compiled routes")


async def _run_requests(app, payloads: list[Mapping[str, Any] | list[Any]]) -> list[Mapping[str, Any]]:
    results: list[Mapping[str, Any]] = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://demo.local",
    ) as client:
        for payload in payloads:
            response = await client.post(f"/routes/{DEMO_ROUTE_ID}/append", json=payload)
            entry: Mapping[str, Any] = {
                "command": f"POST /routes/{DEMO_ROUTE_ID}/append",
                "payload": payload,
                "status": response.status_code,
                "response": response.json(),
                "headers": dict(response.headers),
            }
            results.append(entry)
    return results


def _build_markdown(data: Mapping[str, Any]) -> str:
    route_id = data["route_id"]
    append_path = data["append_path"]
    lines: list[str] = []
    lines.append("# Data Append Demo")
    lines.append("")
    lines.append(
        "This transcript was generated by running the live append workflow against the "
        f"`{route_id}` route. The script resets `runtime/appends`, records every request, "
        "captures the resulting files, and restores the original storage afterwards."
    )
    lines.append("")

    reset = data["reset"]
    lines.append("## Resetting append storage")
    lines.append("")
    lines.append("**Before reset**")
    lines.append("")
    lines.append("```text")
    lines.append(reset["before"]["tree"] or "(empty)")
    lines.append("```")
    lines.append("")
    lines.append("**After reset**")
    lines.append("")
    lines.append("```text")
    lines.append(reset["after"]["tree"] or "(empty)")
    lines.append("```")
    lines.append("")

    lines.append("## Append requests")
    lines.append("")
    for index, request in enumerate(data["requests"], start=1):
        label = request.get("label", f"Request {index}")
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"Command: `{request['command']}`")
        lines.append("")
        lines.append("**Payload**")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(request["payload"], indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")
        lines.append(f"Status: `{request['status']}`")
        lines.append("")
        lines.append("**Response**")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(request["response"], indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")

    lines.append("## Filesystem snapshot during run")
    lines.append("")
    lines.append("```text")
    lines.append(data["filesystem"]["tree"])
    lines.append("```")
    lines.append("")

    csv_data = data["csv"]
    lines.append("## Appended CSV contents")
    lines.append("")
    lines.append(f"Command: `cat {append_path}`")
    lines.append("")
    lines.append("```csv")
    lines.append(csv_data["content"].strip())
    lines.append("```")
    lines.append("")

    return "\n".join(lines) + "\n"


def _assemble_capture(
    config: Config,
    route: RouteDefinition,
    reset_ctx: AppendStorageReset,
    requests: list[Mapping[str, Any]],
    filesystem: DirectorySnapshot,
    csv_content: str,
) -> Mapping[str, Any]:
    append_meta = route.metadata.get("append") if isinstance(route.metadata, Mapping) else None
    if not isinstance(append_meta, Mapping):
        raise RuntimeError("Route is missing append metadata")

    append_destination = str(append_meta.get("destination") or f"{route.id}.csv")
    append_path = (config.server.storage_root / "runtime" / "appends" / append_destination).resolve()
    relative_append_path = append_path.relative_to(config.server.storage_root).as_posix()

    request_entries: list[Mapping[str, Any]] = []
    for entry in requests:
        label = "Happy path append" if entry["status"] < 400 else "Validation failure"
        request_entries.append({"label": label, **entry})

    data: dict[str, Any] = {
        "generated_at": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(),
        "storage_root": config.server.storage_root.as_posix(),
        "route_id": route.id,
        "route_path": route.path,
        "append_path": relative_append_path,
        "reset": {
            "before": dataclasses.asdict(reset_ctx.before) if reset_ctx.before else {},
            "after": dataclasses.asdict(reset_ctx.after_reset) if reset_ctx.after_reset else {},
        },
        "requests": request_entries,
        "filesystem": dataclasses.asdict(filesystem),
        "csv": {
            "path": relative_append_path,
            "content": csv_content,
        },
    }
    return data


async def generate() -> None:
    demo_dir = Path(__file__).resolve().parent
    repo_root = demo_dir.parent.parent

    data: Mapping[str, Any] | None = None
    with tempfile.TemporaryDirectory(prefix="append-demo-", dir=demo_dir) as temp_storage:
        storage_override = Path(temp_storage)
        config = _prepare_config(repo_root, storage_override=storage_override)
        compile_routes(config.server.source_dir, config.server.build_dir)
        routes = load_compiled_routes(config.server.build_dir)
        route = _select_route(routes, DEMO_ROUTE_ID)

        os.environ.setdefault("WEBDUCK_SKIP_CHARTJS_DOWNLOAD", "1")
        app = create_app(routes, config)
        append_meta = route.metadata.get("append") if isinstance(route.metadata, Mapping) else {}
        destination = str(append_meta.get("destination") or f"{route.id}.csv")

        payloads: list[Any] = [
            {
                "greeting": "Hello, append demo!",
                "note": "Captured by demos/data-append/generate_demo.py",
                "created_at": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(),
            },
            [
                {
                    "greeting": "Ignored row",
                }
            ],
        ]

        with AppendStorageReset(config.server.storage_root) as reset_ctx:
            requests = await _run_requests(app, payloads)
            appends_dir = config.server.storage_root / "runtime" / "appends"
            filesystem_snapshot = _capture_directory(appends_dir, relative_to=config.server.storage_root)
            csv_destination = (appends_dir / destination).resolve()
            csv_text = csv_destination.read_text(encoding="utf-8")

            data = _assemble_capture(config, route, reset_ctx, requests, filesystem_snapshot, csv_text)

        app = None  # allow GC to release storage-backed helpers
        gc.collect()

    if data is None:
        raise RuntimeError("Failed to capture append demo results")

    captures_path = demo_dir / "captures.json"
    captures_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    markdown = _build_markdown(data)
    (demo_dir / "demo.md").write_text(markdown, encoding="utf-8")


def main() -> None:
    asyncio.run(generate())


if __name__ == "__main__":
    main()
