from __future__ import annotations

import json
import re
import shutil
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from webbed_duck.config import Config, load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.local import LocalRouteRunner, run_route
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app
from webbed_duck.server.execution import RouteExecutor

DEMO_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = DEMO_DIR / "_workspace"
SRC_DIR = WORKSPACE_DIR / "routes_src"
BUILD_DIR = WORKSPACE_DIR / "routes_build"
STORAGE_DIR = WORKSPACE_DIR / "storage"
DEMO_PATH = DEMO_DIR / "demo.md"
ROUTE_SOURCE = DEMO_DIR / "routes_src"


def _sanitize_mermaid_identifier(label: str, *, used: set[str]) -> str:
    """Return a Mermaid-safe identifier that is stable for a given label."""

    base = re.sub(r"[^0-9A-Za-z_]", "_", label)
    if not base:
        base = "node"
    if base[0].isdigit():
        base = f"n_{base}"
    candidate = base
    counter = 1
    while candidate in used:
        candidate = f"{base}_{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def _escape_mermaid_text(text: str) -> str:
    """Escape text for inclusion inside Mermaid node labels."""

    return text.replace("\\", "\\\\").replace("\"", "\\\"")


def _normalize_dependency_target(target: str) -> str:
    """Normalize dependency targets to their route identifiers."""

    if not target:
        return target
    if target.startswith("local:"):
        target = target.split(":", 1)[1]
    if "?" in target:
        target = target.split("?", 1)[0]
    return target


def _build_dependency_diagram(root_route: str, dependencies: list[Mapping[str, Any]]) -> str:
    """Generate a Mermaid flowchart for the captured dependency chain."""

    used_ids: set[str] = set()
    node_ids: dict[str, str] = {}
    nodes: set[str] = {root_route}

    normalized_dependencies: list[tuple[str, str, str]] = []
    for dep in dependencies:
        parent = dep.get("parent") or root_route
        target = _normalize_dependency_target(str(dep.get("target", "")))
        alias = str(dep.get("alias", "")).strip()
        if parent:
            nodes.add(parent)
        if target:
            nodes.add(target)
        normalized_dependencies.append((parent or root_route, alias, target))

    for label in sorted(nodes):
        node_ids[label] = _sanitize_mermaid_identifier(label, used=used_ids)

    lines = ["flowchart TD"]
    for label, identifier in sorted(node_ids.items(), key=lambda item: item[0]):
        lines.append(f'    {identifier}["{_escape_mermaid_text(label)}"]')

    for parent, alias, target in normalized_dependencies:
        if not target:
            continue
        parent_id = node_ids[parent]
        target_id = node_ids[target]
        alias_label = alias.replace("|", "/").replace("\n", " ").replace("\\", "\\\\").replace("\"", "'")
        if alias_label:
            lines.append(f"    {parent_id} -->|{alias_label}| {target_id}")
        else:
            lines.append(f"    {parent_id} --> {target_id}")

    if len(lines) == 1:
        # No dependencies at all; render the root node for completeness.
        identifier = node_ids[root_route]
        lines.append(f'    {identifier}["{_escape_mermaid_text(root_route)}"]')

    return "\n".join(lines)


def _load_route_sources() -> dict[str, dict[str, str]]:
    sources: dict[str, dict[str, str]] = {}
    for path in ROUTE_SOURCE.glob("*.*"):
        if path.suffix not in {".sql", ".toml"}:
            continue
        route_sources = sources.setdefault(path.stem, {})
        route_sources[path.suffix.lstrip(".")] = path.read_text(encoding="utf-8")
    return sources


@dataclass(slots=True)
class DemoEntry:
    """Single transcript item captured by the generator."""

    title: str
    command: str
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    error: str | None = None
    meta: dict[str, Any] | None = None
    diagrams: list[tuple[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class DemoRecorder:
    """Collect commands and format them into Markdown."""

    entries: list[DemoEntry] = field(default_factory=list)
    toggles: dict[str, dict[str, Any]] = field(default_factory=dict)
    route_sources: dict[str, dict[str, str]] = field(default_factory=dict)

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
            for title, diagram in entry.diagrams:
                lines.append(f"**{title}**")
                lines.append("")
                lines.append("```mermaid")
                lines.extend(diagram.splitlines())
                lines.append("```")
                lines.append("")
            if entry.error is not None:
                lines.append("**Error**")
                lines.append("")
                lines.append("```text")
                lines.append(entry.error.strip())
                lines.append("```")
                lines.append("")
        if self.route_sources:
            lines.append("## Route Source Files")
            lines.append("")
            for route_id in sorted(self.route_sources):
                files = self.route_sources[route_id]
                lines.append(f"### {route_id}")
                lines.append("")
                toml_text = files.get("toml")
                if toml_text is not None:
                    lines.append("```toml")
                    lines.append(toml_text.rstrip())
                    lines.append("```")
                    lines.append("")
                sql_text = files.get("sql")
                if sql_text is not None:
                    lines.append("```sql")
                    lines.append(sql_text.rstrip())
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
    for source in ROUTE_SOURCE.iterdir():
        if not source.is_file():
            continue
        destination = SRC_DIR / source.name
        shutil.copy2(source, destination)


def _serialize_records(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        return {"rows": data}
    return {"result": data}


def _run_with_cache_capture(runner: LocalRouteRunner, **kwargs: Any) -> tuple[Any, dict[str, Any]]:
    captured: dict[str, Any] = {}
    call_sequence: list[dict[str, Any]] = []
    dependencies: list[dict[str, Any]] = []
    original_run_relation = RouteExecutor._run_relation  # type: ignore[attr-defined]
    original_register_dependency = RouteExecutor._register_dependency  # type: ignore[attr-defined]

    def wrapped_run_relation(self: RouteExecutor, route, prepared, **inner_kwargs):  # type: ignore[override]
        result = original_run_relation(self, route, prepared, **inner_kwargs)
        call_sequence.append(
            {
                "route_id": route.id,
                "used_cache": result.used_cache,
                "cache_hit": result.cache_hit,
                "total_rows": result.total_rows,
                "applied_offset": result.applied_offset,
                "applied_limit": result.applied_limit,
            }
        )
        return result

    def wrapped_register_dependency(self: RouteExecutor, con, route, params, use, **inner_kwargs):  # type: ignore[override]
        dependencies.append({"parent": route.id, "alias": use.alias, "target": use.call})
        return original_register_dependency(self, con, route, params, use, **inner_kwargs)

    RouteExecutor._run_relation = wrapped_run_relation  # type: ignore[assignment]
    RouteExecutor._register_dependency = wrapped_register_dependency  # type: ignore[assignment]
    try:
        output = runner.run(**kwargs)
    finally:
        RouteExecutor._run_relation = original_run_relation  # type: ignore[assignment]
        RouteExecutor._register_dependency = original_register_dependency  # type: ignore[assignment]

    if call_sequence:
        final = call_sequence[-1]
        captured.update(
            {
                "used_cache": final["used_cache"],
                "cache_hit": final["cache_hit"],
                "total_rows": final["total_rows"],
                "applied_offset": final["applied_offset"],
                "applied_limit": final["applied_limit"],
            }
        )
    captured["call_sequence"] = call_sequence
    captured["dependencies"] = [
        {
            "parent": dep.get("parent"),
            "alias": dep.get("alias"),
            "target": _normalize_dependency_target(str(dep.get("target", ""))),
        }
        for dep in dependencies
    ]
    captured["dependency_diagram"] = _build_dependency_diagram(
        str(kwargs.get("route_id", "route")), captured["dependencies"]
    )
    return output, captured


def _format_meta(meta: Mapping[str, Any]) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    formatted: dict[str, Any] = {}
    diagrams: list[tuple[str, str]] = []
    for key in ("used_cache", "cache_hit", "total_rows", "applied_offset", "applied_limit"):
        if key in meta:
            formatted[key] = meta[key]
    if meta.get("call_sequence"):
        formatted["call_sequence"] = json.dumps(meta["call_sequence"], indent=2)
    if meta.get("dependencies"):
        formatted["dependencies"] = json.dumps(meta["dependencies"], indent=2)
    diagram_text = meta.get("dependency_diagram")
    if isinstance(diagram_text, str) and diagram_text.strip():
        diagrams.append(("Dependency Diagram", diagram_text))
    return formatted, diagrams


def generate_demo() -> None:
    recorder = DemoRecorder()
    recorder.route_sources = _load_route_sources()
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

        prefix_run, prefix_meta = _run_with_cache_capture(
            runner,
            route_id="traceability_prefix_map",
            params={"prefix": "PN"},
            format="records",
        )
        prefix_notes, prefix_diagrams = _format_meta(prefix_meta)
        recorder.add(
            DemoEntry(
                title="Prefix mapping lookup",
                command="runner.run(route_id=\"traceability_prefix_map\", params={\"prefix\": \"PN\"}, format=\"records\")",
                response=_serialize_records(prefix_run),
                meta=prefix_notes,
                diagrams=prefix_diagrams,
            )
        )

        panel_run, panel_meta = _run_with_cache_capture(
            runner,
            route_id="traceability_panel_events",
            params={"barcode": "PN-1001"},
            format="records",
        )
        panel_notes, panel_diagrams = _format_meta(panel_meta)
        recorder.add(
            DemoEntry(
                title="Panel events lookup",
                command="runner.run(route_id=\"traceability_panel_events\", params={\"barcode\": \"PN-1001\"}, format=\"records\")",
                response=_serialize_records(panel_run),
                meta=panel_notes,
                diagrams=panel_diagrams,
            )
        )

        summary_params = {"barcode": "PN-1001"}
        summary_run, summary_meta = _run_with_cache_capture(
            runner,
            route_id="traceability_barcode_summary",
            params=summary_params,
            format="records",
        )
        summary_notes, summary_diagrams = _format_meta(summary_meta)
        recorder.add(
            DemoEntry(
                title="Traceability summary first execution",
                command="runner.run(route_id=\"traceability_barcode_summary\", params={\"barcode\": \"PN-1001\"}, format=\"records\")",
                response=_serialize_records(summary_run),
                meta=summary_notes,
                diagrams=summary_diagrams,
            )
        )

        summary_cached_run, summary_cached_meta = _run_with_cache_capture(
            runner,
            route_id="traceability_barcode_summary",
            params=summary_params,
            format="records",
        )
        summary_cached_notes, summary_cached_diagrams = _format_meta(summary_cached_meta)
        recorder.add(
            DemoEntry(
                title="Traceability summary cached execution",
                command="runner.run(route_id=\"traceability_barcode_summary\", params={\"barcode\": \"PN-1001\"}, format=\"records\")",
                response=_serialize_records(summary_cached_run),
                meta=summary_cached_notes,
                diagrams=summary_cached_diagrams,
            )
        )

        module_summary_run, module_summary_meta = _run_with_cache_capture(
            runner,
            route_id="traceability_barcode_summary",
            params={"barcode": "MD-5005"},
            format="records",
        )
        module_notes, module_diagrams = _format_meta(module_summary_meta)
        recorder.add(
            DemoEntry(
                title="Traceability summary for module barcode",
                command="runner.run(route_id=\"traceability_barcode_summary\", params={\"barcode\": \"MD-5005\"}, format=\"records\")",
                response=_serialize_records(module_summary_run),
                meta=module_notes,
                diagrams=module_diagrams,
            )
        )

        baseline = run_route(
            "traceability_barcode_summary",
            {"barcode": "PN-1001"},
            routes=routes,
            config=config,
            format="records",
        )
        recorder.add(
            DemoEntry(
                title="run_route summary baseline",
                command="run_route(\"traceability_barcode_summary\", {\"barcode\": \"PN-1001\"}, routes=routes, config=config, format=\"records\")",
                response=_serialize_records(baseline),
            )
        )

        app = create_app(routes, config)
        client = TestClient(app)

        http_payload = {
            "reference": "local:traceability_barcode_summary?column=table_route&column=event_time&column=status",
            "params": {"barcode": "PN-1001"},
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
