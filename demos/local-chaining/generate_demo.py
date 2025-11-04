from __future__ import annotations

import json
import shutil
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from webbed_duck.config import Config, load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.local import LocalRouteRunner, RouteNotFoundError, run_route
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app
from webbed_duck.server.execution import RouteExecutor
from webbed_duck.server.overlay import OverlayStore, compute_row_key_from_values

DEMO_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = DEMO_DIR / "_workspace"
SRC_DIR = WORKSPACE_DIR / "routes_src"
BUILD_DIR = WORKSPACE_DIR / "routes_build"
STORAGE_DIR = WORKSPACE_DIR / "storage"
DEMO_PATH = DEMO_DIR / "demo.md"
ROUTE_SOURCE = Path("routes_src")


@dataclass(slots=True)
class DemoEntry:
    """Single transcript item captured by the generator."""

    title: str
    command: str
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    error: str | None = None
    meta: dict[str, Any] | None = None


@dataclass(slots=True)
class DemoRecorder:
    """Collect commands and format them into Markdown."""

    entries: list[DemoEntry] = field(default_factory=list)
    toggles: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add(self, entry: DemoEntry) -> None:
        self.entries.append(entry)

    def set_toggle(self, name: str, before: Any, after: Any) -> None:
        self.toggles[name] = {"before": before, "after": after}

    def to_markdown(self, *, generated_at: datetime) -> str:
        lines: list[str] = []
        lines.append("<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->")
        lines.append("# Local Route Chaining Demo")
        lines.append("")
        lines.append(f"Generated on {generated_at.isoformat()} UTC.")
        lines.append("")
        if self.toggles:
            lines.append("## Feature & Auth Toggles")
            lines.append("")
            lines.append("These toggles were applied during the run and restored afterwards:")
            lines.append("")
            for name, values in sorted(self.toggles.items()):
                before = json.dumps(values["before"], sort_keys=True)
                after = json.dumps(values["after"], sort_keys=True)
                lines.append(f"- **{name}**: {before} → {after}")
            lines.append("")
        lines.append("## Command Transcript")
        lines.append("")
        for index, entry in enumerate(self.entries, start=1):
            lines.append(f"### {index}. {entry.title}")
            lines.append("")
            lines.append("**Command**")
            lines.append("")
            lines.append("```python")
            lines.append(entry.command.strip())
            lines.append("```")
            lines.append("")
            if entry.request is not None:
                lines.append("**Request JSON**")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(entry.request, indent=2, sort_keys=True))
                lines.append("```")
                lines.append("")
            if entry.response is not None:
                lines.append("**Response JSON**")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(entry.response, indent=2, sort_keys=True))
                lines.append("```")
                lines.append("")
            if entry.meta:
                lines.append("**Notes**")
                lines.append("")
                for key, value in entry.meta.items():
                    lines.append(f"- {key}: {value}")
                lines.append("")
            if entry.error is not None:
                lines.append("**Error**")
                lines.append("")
                lines.append("```text")
                lines.append(entry.error.strip())
                lines.append("```")
                lines.append("")
        return "\n".join(lines).strip() + "\n"


@contextmanager
def toggled_config(config: Config, *, overrides_enabled: bool, auth_mode: str) -> Iterator[dict[str, Any]]:
    """Temporarily toggle configuration values for the demo run."""

    original = {
        "feature_flags.overrides_enabled": config.feature_flags.overrides_enabled,
        "auth.mode": config.auth.mode,
    }
    config.feature_flags.overrides_enabled = overrides_enabled
    config.auth.mode = auth_mode
    try:
        yield original
    finally:
        config.feature_flags.overrides_enabled = original["feature_flags.overrides_enabled"]
        config.auth.mode = original["auth.mode"]


def _reset_workspace() -> None:
    if WORKSPACE_DIR.exists():
        shutil.rmtree(WORKSPACE_DIR)
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def _seed_routes() -> None:
    for source in ROUTE_SOURCE.glob("hello.*"):
        destination = SRC_DIR / source.name
        shutil.copy2(source, destination)


def _serialize_records(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        return {"rows": data}
    return {"result": data}


def _run_with_cache_capture(runner: LocalRouteRunner, **kwargs: Any) -> tuple[Any, dict[str, Any]]:
    captured: dict[str, Any] = {}
    original = RouteExecutor.execute_relation

    def wrapped(self: RouteExecutor, route, params, **inner_kwargs):  # type: ignore[override]
        result = original(self, route, params, **inner_kwargs)
        captured.update(
            {
                "used_cache": result.used_cache,
                "cache_hit": result.cache_hit,
                "total_rows": result.total_rows,
                "applied_offset": result.applied_offset,
                "applied_limit": result.applied_limit,
            }
        )
        return result

    RouteExecutor.execute_relation = wrapped  # type: ignore[assignment]
    try:
        output = runner.run(**kwargs)
    finally:
        RouteExecutor.execute_relation = original  # type: ignore[assignment]
    return output, captured


def generate_demo() -> None:
    recorder = DemoRecorder()
    _reset_workspace()
    _seed_routes()
    compiled = compile_routes(SRC_DIR, BUILD_DIR)
    recorder.add(
        DemoEntry(
            title="Compile routes",
            command="compile_routes(SRC_DIR, BUILD_DIR)",
            response={"compiled_route_ids": [route.id for route in compiled]},
        )
    )
    routes = load_compiled_routes(BUILD_DIR)

    config = load_config(None)
    config.server.storage_root = STORAGE_DIR
    config.server.source_dir = SRC_DIR
    config.server.build_dir = BUILD_DIR

    with toggled_config(config, overrides_enabled=True, auth_mode="pseudo") as original_values:
        for name, before in original_values.items():
            if name == "feature_flags.overrides_enabled":
                after = config.feature_flags.overrides_enabled
            elif name == "auth.mode":
                after = config.auth.mode
            else:  # pragma: no cover - defensive fallback for future toggles
                after = getattr(config, name, None)
            recorder.set_toggle(name, before=before, after=after)

        runner = LocalRouteRunner(routes=routes, config=config)

        first_run, first_meta = _run_with_cache_capture(
            runner,
            route_id="hello_world",
            params={"name": "Ada"},
            format="records",
        )
        recorder.add(
            DemoEntry(
                title="LocalRouteRunner first execution",
                command="runner.run(route_id=\"hello_world\", params={\"name\": \"Ada\"}, format=\"records\")",
                response=_serialize_records(first_run),
                meta=first_meta,
            )
        )

        second_run, second_meta = _run_with_cache_capture(
            runner,
            route_id="hello_world",
            params={"name": "Ada"},
            format="records",
        )
        recorder.add(
            DemoEntry(
                title="LocalRouteRunner cached execution",
                command="runner.run(route_id=\"hello_world\", params={\"name\": \"Ada\"}, format=\"records\")",
                response=_serialize_records(second_run),
                meta=second_meta,
            )
        )

        baseline = run_route(
            "hello_world",
            {"name": "Ada"},
            routes=routes,
            config=config,
            format="records",
        )
        recorder.add(
            DemoEntry(
                title="run_route baseline",
                command="run_route(\"hello_world\", {\"name\": \"Ada\"}, routes=routes, config=config, format=\"records\")",
                response=_serialize_records(baseline),
            )
        )

        try:
            runner.run(route_id="missing_route")
        except RouteNotFoundError as exc:
            recorder.add(
                DemoEntry(
                    title="LocalRouteRunner error path",
                    command="runner.run(route_id=\"missing_route\")",
                    error=str(exc),
                )
            )

        overlay_store = OverlayStore(STORAGE_DIR)
        row_key = compute_row_key_from_values({"greeting": "Hello, Ada!"}, ["greeting"])
        override = overlay_store.upsert(
            route_id="hello_world",
            row_key=row_key,
            column="note",
            value="Override injected by demo",
            reason="Demo override",
            author="demo",
        )
        recorder.add(
            DemoEntry(
                title="Overlay override applied",
                command="overlay_store.upsert(route_id=\"hello_world\", row_key=row_key, column=\"note\", value=\"Override injected by demo\", reason=\"Demo override\", author=\"demo\")",
                response=override.to_dict(),
            )
        )

        override_run, override_meta = _run_with_cache_capture(
            runner,
            route_id="hello_world",
            params={"name": "Ada"},
            format="records",
        )
        recorder.add(
            DemoEntry(
                title="LocalRouteRunner after override",
                command="runner.run(route_id=\"hello_world\", params={\"name\": \"Ada\"}, format=\"records\")",
                response=_serialize_records(override_run),
                meta=override_meta,
            )
        )

        app = create_app(routes, config)
        client = TestClient(app)
        client.app.state.overlays.reload()

        http_payload = {
            "reference": "local:hello_world?column=greeting&column=note",
            "params": {"name": "Ada"},
            "format": "json",
            "record_analytics": True,
        }
        http_response = client.post("/local/resolve", json=http_payload)
        recorder.add(
            DemoEntry(
                title="HTTP /local/resolve",
                command="client.post(\"/local/resolve\", json=http_payload)",
                request=http_payload,
                response=http_response.json(),
                meta={"status_code": http_response.status_code},
            )
        )

        error_response = client.post("/local/resolve", json={})
        recorder.add(
            DemoEntry(
                title="HTTP /local/resolve error",
                command="client.post(\"/local/resolve\", json={})",
                request={},
                response=error_response.json(),
                meta={"status_code": error_response.status_code},
            )
        )

    shutil.rmtree(WORKSPACE_DIR, ignore_errors=True)

    generated_at = datetime.now(timezone.utc)
    DEMO_PATH.write_text(recorder.to_markdown(generated_at=generated_at), encoding="utf-8")


if __name__ == "__main__":
    generate_demo()
