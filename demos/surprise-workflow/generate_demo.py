"""Generate the Surprise Workflow demo transcript.

This script combines pseudo-auth sessions, append storage, cell overrides,
local route chaining, and share links into a single guided flow. Run it to
refresh ``demo.md`` with a fresh capture.
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from webbed_duck.config import Config, load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.overlay import compute_row_key_from_values
from webbed_duck.server.app import create_app


DEMO_DIR = Path(__file__).resolve().parent
WORKSPACE = DEMO_DIR / "_workspace"
SRC_DIR = WORKSPACE / "routes_src"
BUILD_DIR = WORKSPACE / "routes_build"
STORAGE_ROOT = WORKSPACE / "storage"
DEMO_MD = DEMO_DIR / "demo.md"


@dataclass(slots=True)
class HTTPInteraction:
    """Capture a single HTTP exchange for the transcript."""

    title: str
    method: str
    path: str
    params: Mapping[str, Any] | None = None
    request_json: Mapping[str, Any] | None = None
    status_code: int = 0
    response_json: Any | None = None
    notes: list[str] = field(default_factory=list)

    def to_markdown(self, step_number: int) -> str:
        lines: list[str] = []
        lines.append(f"### {step_number}. {self.title}")
        lines.append("")
        lines.append("**Request**")
        lines.append("")
        request_line = self.path
        if self.params:
            query = urlencode(self.params, doseq=True)
            request_line = f"{self.path}?{query}"
        lines.append("```http")
        lines.append(f"{self.method.upper()} {request_line} HTTP/1.1")
        lines.append("host: testserver")
        lines.append("user-agent: demo-generator")
        lines.append("accept: application/json")
        lines.append("```")
        if self.request_json is not None:
            lines.append("")
            lines.append("**Request JSON**")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(self.request_json, indent=2, sort_keys=True))
            lines.append("```")
        lines.append("")
        lines.append("**Response JSON**")
        lines.append("")
        lines.append("```json")
        payload = {"status_code": self.status_code, "body": self.response_json}
        lines.append(json.dumps(payload, indent=2, sort_keys=True))
        lines.append("```")
        if self.notes:
            lines.append("")
            lines.append("**Why it matters**")
            lines.append("")
            for note in self.notes:
                lines.append(f"- {note}")
        lines.append("")
        return "\n".join(lines)


def _reset_workspace() -> None:
    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE)
    SRC_DIR.mkdir(parents=True)
    BUILD_DIR.mkdir(parents=True)
    STORAGE_ROOT.mkdir(parents=True)


def _seed_routes() -> None:
    source_dir = REPO_ROOT / "routes_src"
    for path in source_dir.iterdir():
        if path.is_file():
            shutil.copy2(path, SRC_DIR / path.name)


def _configure(config: Config) -> None:
    config.server.storage_root = STORAGE_ROOT
    config.server.source_dir = SRC_DIR
    config.server.build_dir = BUILD_DIR
    config.auth.mode = "pseudo"
    flags = config.feature_flags
    flags.overrides_enabled = True
    flags.annotations_enabled = True
    flags.comments_enabled = True
    flags.tasks_enabled = True


def _format_csv(path: Path) -> str:
    if not path.exists():
        return "(missing)"
    return path.read_text(encoding="utf-8").strip()


def _format_overrides(payload: Mapping[str, Any] | None) -> str:
    if not payload:
        return "(none recorded)"
    return json.dumps(payload, indent=2, sort_keys=True)


def generate_demo() -> None:
    _reset_workspace()
    _seed_routes()
    compile_routes(SRC_DIR, BUILD_DIR)
    routes = load_compiled_routes(BUILD_DIR)

    config = load_config(None)
    _configure(config)

    app = create_app(routes, config)
    client = TestClient(app)

    interactions: list[HTTPInteraction] = []
    generated_at = datetime.now(timezone.utc)

    surprise_name = "Surprise Workflow"
    greeting = f"Hello, {surprise_name}!"
    csv_snapshot: str = ""
    overrides_snapshot: Mapping[str, Any] | None = None

    login_payload = {"email": "analyst@example.com", "remember_me": False}
    login_response = client.post("/auth/pseudo/session", json=login_payload)
    interactions.append(
        HTTPInteraction(
            title="Start pseudo session",
            method="POST",
            path="/auth/pseudo/session",
            request_json=login_payload,
            status_code=login_response.status_code,
            response_json=login_response.json(),
            notes=["Creates a pseudo-auth session so overrides and shares capture the analyst's identity."],
        )
    )

    schema_response = client.get("/routes/hello_world/schema")
    interactions.append(
        HTTPInteraction(
            title="Inspect route schema and form metadata",
            method="GET",
            path="/routes/hello_world/schema",
            status_code=schema_response.status_code,
            response_json=schema_response.json(),
            notes=[
                "Shows the auto-generated parameter form and the override/append capabilities baked into the route metadata.",
            ],
        )
    )

    first_query_params = {"format": "json", "name": surprise_name}
    first_response = client.get("/hello", params=first_query_params)
    interactions.append(
        HTTPInteraction(
            title="Render the greeting before overrides",
            method="GET",
            path="/hello",
            params=first_query_params,
            status_code=first_response.status_code,
            response_json=first_response.json(),
            notes=["Baseline JSON response that will be augmented by later steps."],
        )
    )

    append_payload = {
        "greeting": greeting,
        "note": "Appended from the surprise workflow demo",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    append_response = client.post("/routes/hello_world/append", json=append_payload)
    interactions.append(
        HTTPInteraction(
            title="Persist the greeting via CSV append",
            method="POST",
            path="/routes/hello_world/append",
            request_json=append_payload,
            status_code=append_response.status_code,
            response_json=append_response.json(),
            notes=[
                "Captures the live greeting in append storage so downstream tools can reuse it without re-running the query.",
            ],
        )
    )

    append_path = Path(append_response.json().get("path", ""))
    if not append_path.is_absolute():
        append_path = (STORAGE_ROOT / append_path).resolve()
    csv_snapshot = _format_csv(append_path)

    row_key = compute_row_key_from_values({"greeting": greeting}, ["greeting"])
    override_payload = {
        "column": "note",
        "row_key": row_key,
        "value": "Blends append storage with a live override to narrate the workflow.",
        "reason": "Annotate the persisted greeting for teammates",
        "author": "demo-bot",
    }
    override_response = client.post("/routes/hello_world/overrides", json=override_payload)
    interactions.append(
        HTTPInteraction(
            title="Apply a cell-level override",
            method="POST",
            path="/routes/hello_world/overrides",
            request_json=override_payload,
            status_code=override_response.status_code,
            response_json=override_response.json(),
            notes=[
                "Overrides the note column for this specific greeting so collaborators see curated guidance next to the data.",
            ],
        )
    )

    refreshed_response = client.get("/hello", params=first_query_params)
    interactions.append(
        HTTPInteraction(
            title="Re-run the greeting with overrides applied",
            method="GET",
            path="/hello",
            params=first_query_params,
            status_code=refreshed_response.status_code,
            response_json=refreshed_response.json(),
            notes=[
                "Shows the override being layered on top of the cached query result — no SQL edits required.",
            ],
        )
    )

    local_payload = {
        "reference": "local:hello_world",
        "params": {"name": surprise_name},
        "columns": ["greeting", "note"],
        "format": "json",
        "record_analytics": False,
    }
    local_response = client.post("/local/resolve", json=local_payload)
    interactions.append(
        HTTPInteraction(
            title="Resolve the same slice through /local/resolve",
            method="POST",
            path="/local/resolve",
            request_json=local_payload,
            status_code=local_response.status_code,
            response_json=local_response.json(),
            notes=[
                "Demonstrates chaining the curated slice inside other routes or automations without touching HTTP clients.",
            ],
        )
    )

    share_payload = {
        "emails": ["teammate@example.com"],
        "format": "json",
        "params": {"name": surprise_name},
    }
    share_response = client.post("/routes/hello_world/share", json=share_payload)
    share_json = share_response.json()
    interactions.append(
        HTTPInteraction(
            title="Create a share link with the curated slice",
            method="POST",
            path="/routes/hello_world/share",
            request_json=share_payload,
            status_code=share_response.status_code,
            response_json=share_json,
            notes=[
                "Bundles the override-enhanced view so teammates receive the annotated greeting and Arrow/JSON attachments.",
            ],
        )
    )

    token = share_json.get("share", {}).get("token")
    if token:
        share_fetch = client.get(f"/shares/{token}", params={"format": "json"})
        interactions.append(
            HTTPInteraction(
                title="Resolve the share token",
                method="GET",
                path=f"/shares/{token}",
                params={"format": "json"},
                status_code=share_fetch.status_code,
                response_json=share_fetch.json(),
                notes=[
                    "Verifies that the public share faithfully reproduces the overridden note without re-authenticating.",
                ],
            )
        )

    overrides_response = client.get("/routes/hello_world/overrides")
    overrides_snapshot = overrides_response.json()

    markdown_lines: list[str] = []
    markdown_lines.append("<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->")
    markdown_lines.append("# Surprise Workflow Demo")
    markdown_lines.append("")
    markdown_lines.append(f"Generated on {generated_at.isoformat()} UTC.")
    markdown_lines.append("")
    markdown_lines.append(
        "This walk-through stitches together pseudo-auth sessions, append storage, cell overrides, "
        "local route chaining, and share links to showcase how WebDuck workflows compound when orchestrated intentionally."
    )
    markdown_lines.append("")
    markdown_lines.append("## Feature toggles during capture")
    markdown_lines.append("")
    markdown_lines.append("- `auth.mode = \"pseudo\"`")
    markdown_lines.append("- `feature_flags.overrides_enabled = true`")
    markdown_lines.append("- `feature_flags.annotations_enabled = true`")
    markdown_lines.append("- `feature_flags.comments_enabled = true`")
    markdown_lines.append("- `feature_flags.tasks_enabled = true`")
    markdown_lines.append("")
    markdown_lines.append("## HTTP transcript")
    markdown_lines.append("")
    for index, interaction in enumerate(interactions, start=1):
        markdown_lines.append(interaction.to_markdown(index))
    markdown_lines.append("## Append storage snapshot")
    markdown_lines.append("")
    markdown_lines.append("```csv")
    markdown_lines.append(csv_snapshot or "(empty)")
    markdown_lines.append("```")
    markdown_lines.append("")
    markdown_lines.append("## Override ledger")
    markdown_lines.append("")
    markdown_lines.append("```json")
    markdown_lines.append(_format_overrides(overrides_snapshot))
    markdown_lines.append("```")
    markdown_lines.append("")
    DEMO_MD.write_text("\n".join(markdown_lines), encoding="utf-8")


if __name__ == "__main__":
    generate_demo()
