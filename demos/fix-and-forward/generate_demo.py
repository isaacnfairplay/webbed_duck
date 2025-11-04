from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app

DEMO_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = DEMO_DIR / "_workspace"
SRC_DIR = WORKSPACE_DIR / "routes_src"
BUILD_DIR = WORKSPACE_DIR / "routes_build"
STORAGE_DIR = WORKSPACE_DIR / "storage"
ROUTE_SOURCE = Path("routes_src")
DEMO_PATH = DEMO_DIR / "demo.md"


@dataclass(slots=True)
class DemoEntry:
    title: str
    command: str
    request_json: dict[str, Any] | None = None
    query_params: dict[str, Any] | None = None
    response_json: dict[str, Any] | None = None
    response_text: str | None = None
    notes: dict[str, Any] | None = None


@dataclass(slots=True)
class DemoRecorder:
    entries: list[DemoEntry] = field(default_factory=list)
    toggles: dict[str, tuple[Any, Any]] = field(default_factory=dict)

    def add(self, entry: DemoEntry) -> None:
        self.entries.append(entry)

    def set_toggle(self, key: str, before: Any, after: Any) -> None:
        if before != after:
            self.toggles[key] = (before, after)

    def to_markdown(self, generated_at: datetime) -> str:
        lines: list[str] = []
        lines.append("<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->")
        lines.append("# Fix-and-Forward Demo")
        lines.append("")
        lines.append(
            "This walkthrough shows how overrides, append logging, local references, and shares "
            "work together once you start fixing data and immediately forwarding the result."
        )
        lines.append("")
        lines.append(f"Generated on {generated_at.isoformat()} UTC.")
        lines.append("")
        if self.toggles:
            lines.append("## Feature & Auth Toggles")
            lines.append("")
            lines.append("These toggles were applied during the run and restored afterwards:")
            lines.append("")
            for name, (before, after) in sorted(self.toggles.items()):
                before_json = json.dumps(before, sort_keys=True)
                after_json = json.dumps(after, sort_keys=True)
                lines.append(f"- **{name}**: {before_json} → {after_json}")
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
            if entry.query_params:
                lines.append("**Query Parameters**")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(entry.query_params, indent=2, sort_keys=True))
                lines.append("```")
                lines.append("")
            if entry.request_json is not None:
                lines.append("**Request JSON**")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(entry.request_json, indent=2, sort_keys=True))
                lines.append("```")
                lines.append("")
            if entry.response_json is not None:
                lines.append("**Response JSON**")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(entry.response_json, indent=2, sort_keys=True))
                lines.append("```")
                lines.append("")
            if entry.response_text is not None:
                lines.append("**Response**")
                lines.append("")
                lines.append("```text")
                lines.append(entry.response_text.rstrip())
                lines.append("```")
                lines.append("")
            if entry.notes:
                lines.append("**Notes**")
                lines.append("")
                for key, value in entry.notes.items():
                    lines.append(f"- {key}: {value}")
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def _reset_workspace() -> None:
    if WORKSPACE_DIR.exists():
        shutil.rmtree(WORKSPACE_DIR)
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def _seed_routes() -> None:
    for source in ROUTE_SOURCE.glob("hello.*"):
        shutil.copy2(source, SRC_DIR / source.name)


def _json_safe(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(key): _json_safe(value) for key, value in data.items()}
    if isinstance(data, list):
        return [_json_safe(item) for item in data]
    if isinstance(data, (str, int, float, bool)) or data is None:
        return data
    return str(data)


def _record_http(
    recorder: DemoRecorder,
    *,
    title: str,
    command: str,
    response,
    request_json: dict[str, Any] | None = None,
    query_params: dict[str, Any] | None = None,
    extra_notes: dict[str, Any] | None = None,
    response_filter: Callable[[Any], Any] | None = None,
) -> Any:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    text_payload = None
    if payload is None:
        text_payload = response.text
    else:
        if response_filter is not None:
            payload = response_filter(payload)
        payload = _json_safe(payload)
    notes = {"status_code": response.status_code}
    content_type = response.headers.get("content-type")
    if content_type:
        notes["content_type"] = content_type
    if extra_notes:
        notes.update(extra_notes)
    recorder.add(
        DemoEntry(
            title=title,
            command=command,
            request_json=_json_safe(request_json) if request_json is not None else None,
            query_params=_json_safe(query_params) if query_params is not None else None,
            response_json=payload,
            response_text=text_payload,
            notes=notes,
        )
    )
    return payload or text_payload


def generate_demo() -> None:
    recorder = DemoRecorder()
    _reset_workspace()
    _seed_routes()

    compiled = compile_routes(SRC_DIR, BUILD_DIR)
    recorder.add(
        DemoEntry(
            title="Compile demo routes",
            command="compile_routes(SRC_DIR, BUILD_DIR)",
            response_json={"compiled_route_ids": [route.id for route in compiled]},
        )
    )

    routes = load_compiled_routes(BUILD_DIR)
    config = load_config(None)
    config.server.storage_root = STORAGE_DIR
    config.server.source_dir = SRC_DIR
    config.server.build_dir = BUILD_DIR
    config.server.auto_compile = False
    config.server.watch = False

    recorder.set_toggle("auth.mode", config.auth.mode, "pseudo")
    config.auth.mode = "pseudo"
    config.auth.allowed_domains = ["example.com"]

    recorder.set_toggle(
        "feature_flags.overrides_enabled",
        config.feature_flags.overrides_enabled,
        True,
    )
    config.feature_flags.overrides_enabled = True

    config.email.adapter = None

    app = create_app(routes, config)

    with TestClient(app) as client:
        login_payload = {"email": "ops.lead@example.com"}
        login_response = client.post("/auth/pseudo/session", json=login_payload)
        _record_http(
            recorder,
            title="Establish pseudo-auth session",
            command="client.post(\"/auth/pseudo/session\", json={\"email\": \"ops.lead@example.com\"})",
            response=login_response,
            request_json=login_payload,
        )

        query_params = {"name": "River", "format": "json"}
        baseline_response = client.get("/hello", params=query_params)
        baseline_data = _record_http(
            recorder,
            title="Baseline hello route response",
            command="client.get(\"/hello\", params={\"name\": \"River\", \"format\": \"json\"})",
            response=baseline_response,
            query_params=query_params,
        )
        greeting = baseline_data["rows"][0]["greeting"] if baseline_data else "Hello, River!"

        override_payload = {
            "column": "note",
            "key": {"greeting": greeting},
            "value": "Ops fix: River is remote-first",
            "reason": "Document remote context before sharing",
        }
        override_response = client.post(
            "/routes/hello_world/overrides",
            json=override_payload,
        )
        override_data = _record_http(
            recorder,
            title="Apply per-cell override to annotate the note",
            command="client.post(\"/routes/hello_world/overrides\", json=override_payload)",
            response=override_response,
            request_json=override_payload,
        )

        annotated_response = client.get("/hello", params=query_params)
        _record_http(
            recorder,
            title="Route response after override",
            command="client.get(\"/hello\", params={\"name\": \"River\", \"format\": \"json\"})",
            response=annotated_response,
            query_params=query_params,
        )

        append_payload = {
            "greeting": greeting,
            "note": override_payload["value"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        append_response = client.post(
            "/routes/hello_world/append",
            json=append_payload,
        )
        append_result = _record_http(
            recorder,
            title="Log the decision via append",
            command="client.post(\"/routes/hello_world/append\", json=append_payload)",
            response=append_response,
            request_json=append_payload,
        )
        append_path = Path(append_result.get("path", "")) if isinstance(append_result, dict) else None
        if append_path and append_path.exists():
            append_text = append_path.read_text(encoding="utf-8")
            recorder.add(
                DemoEntry(
                    title="Inspect append log artifact",
                    command="append_path.read_text(encoding=\"utf-8\")",
                    response_text=append_text,
                    notes={"path": str(append_path)},
                )
            )

        local_payload = {
            "reference": "local:hello_world?column=greeting&column=note",
            "params": {"name": "River"},
            "format": "json",
            "redact_columns": ["note"],
            "record_analytics": False,
        }
        local_response = client.post("/local/resolve", json=local_payload)
        _record_http(
            recorder,
            title="Resolve local reference with redaction for automation",
            command="client.post(\"/local/resolve\", json=local_payload)",
            response=local_response,
            request_json=local_payload,
        )

        share_payload = {
            "emails": ["ally@example.com"],
            "params": {"name": "River"},
            "format": "html_t",
            "max_rows": 1,
        }
        share_response = client.post("/routes/hello_world/share", json=share_payload)
        share_data = _record_http(
            recorder,
            title="Issue a share link without sending email",
            command="client.post(\"/routes/hello_world/share\", json=share_payload)",
            response=share_response,
            request_json=share_payload,
        )
        share_token = ""
        if isinstance(share_data, dict):
            share_token = share_data.get("share", {}).get("token", "")
        if share_token:
            share_fetch_response = client.get(
                f"/shares/{share_token}",
                params={"format": "json", "limit": 1, "column": "greeting"},
            )
            _record_http(
                recorder,
                title="Fetch the shared snapshot as JSON",
                command=(
                    "client.get(f\"/shares/{share_token}\", params={\"format\": \"json\", "
                    "\"limit\": 1, \"column\": \"greeting\"})"
                ),
                response=share_fetch_response,
                query_params={"format": "json", "limit": 1, "column": "greeting"},
            )

        routes_response = client.get("/routes")

        def _route_filter(payload: dict[str, Any]) -> dict[str, Any]:
            routes = payload.get("routes", [])
            hello_summary: dict[str, Any] | None = None
            for item in routes:
                if item.get("id") == "hello_world":
                    hello_summary = {
                        "id": item.get("id"),
                        "title": item.get("title"),
                        "metrics": item.get("metrics"),
                        "overrides": item.get("overrides"),
                        "append": item.get("append"),
                    }
                    break
            return {"route_summary": hello_summary}

        _record_http(
            recorder,
            title="Review route analytics after the workflow",
            command="client.get(\"/routes\")",
            response=routes_response,
            response_filter=_route_filter,
        )

    demo_markdown = recorder.to_markdown(generated_at=datetime.now(timezone.utc))
    DEMO_PATH.write_text(demo_markdown, encoding="utf-8")


if __name__ == "__main__":
    generate_demo()
