"""Generate the annotated share workflow demo from live interactions."""
from __future__ import annotations

import json
import shutil
import sys
import types
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTE_SOURCE = REPO_ROOT / "routes_src"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from webbed_duck.config import Config, load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.local import LocalRouteRunner
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app
from webbed_duck.server.overlay import compute_row_key_from_values

DEMO_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = DEMO_DIR / "_workspace"
SRC_DIR = WORKSPACE_DIR / "routes_src"
BUILD_DIR = WORKSPACE_DIR / "routes_build"
STORAGE_DIR = WORKSPACE_DIR / "storage"
DEMO_PATH = DEMO_DIR / "demo.md"


@dataclass(slots=True)
class Step:
    """Single transcript entry in the walkthrough."""

    title: str
    command: str
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    notes: Sequence[str] = field(default_factory=list)


@dataclass(slots=True)
class Recorder:
    """Collect steps and configuration toggles for Markdown emission."""

    steps: list[Step] = field(default_factory=list)
    toggles: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add_step(
        self,
        *,
        title: str,
        command: str,
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
        notes: Sequence[str] | None = None,
    ) -> None:
        self.steps.append(
            Step(
                title=title,
                command=command,
                request=request,
                response=response,
                notes=list(notes or []),
            )
        )

    def record_toggle(self, name: str, before: Any, after: Any) -> None:
        if before == after:
            return
        self.toggles[name] = {"before": before, "after": after}

    def to_markdown(self, *, generated_at: datetime) -> str:
        lines: list[str] = []
        lines.append("<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->")
        lines.append("# Annotated Share Workflow Demo")
        lines.append("")
        lines.append(
            "This walkthrough combines schema introspection, overlays, local execution,"
            " and multi-format sharing so analysts can see how the pieces fit together."
        )
        lines.append("")
        lines.append(f"Generated on {generated_at.isoformat()} UTC.")
        lines.append("")
        if self.toggles:
            lines.append("## Temporary configuration tweaks")
            lines.append("")
            lines.append("Applied during generation and reverted afterwards:")
            lines.append("")
            for name, values in sorted(self.toggles.items()):
                before = json.dumps(values["before"], sort_keys=True)
                after = json.dumps(values["after"], sort_keys=True)
                lines.append(f"- **{name}**: {before} → {after}")
            lines.append("")
        lines.append("## Walkthrough")
        lines.append("")
        for index, step in enumerate(self.steps, start=1):
            lines.append(f"### {index}. {step.title}")
            lines.append("")
            lines.append("**Command**")
            lines.append("")
            lines.append("```python")
            lines.append(step.command.strip())
            lines.append("```")
            lines.append("")
            if step.request is not None:
                lines.append("**Request JSON**")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(step.request, indent=2, sort_keys=True))
                lines.append("```")
                lines.append("")
            if step.response is not None:
                lines.append("**Response JSON**")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(step.response, indent=2, sort_keys=True))
                lines.append("```")
                lines.append("")
            if step.notes:
                lines.append("**Notes**")
                lines.append("")
                for note in step.notes:
                    lines.append(f"- {note}")
                lines.append("")
        return "\n".join(lines).strip() + "\n"


def _reset_workspace() -> None:
    if WORKSPACE_DIR.exists():
        shutil.rmtree(WORKSPACE_DIR)
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def _seed_routes() -> None:
    for path in ROUTE_SOURCE.glob("*"):
        if path.is_file():
            shutil.copy2(path, SRC_DIR / path.name)


def _install_email_sink() -> tuple[str, list[tuple]]:
    module_name = "annotated_share_email_sink"
    sink = types.ModuleType(module_name)
    sent: list[tuple] = []

    def send_email(to_addrs, subject, html_body, text_body=None, attachments=None):
        sent.append((tuple(to_addrs), subject, html_body, text_body, attachments))

    sink.send_email = send_email  # type: ignore[attr-defined]
    sys.modules[module_name] = sink
    return module_name, sent


def _configure(recorder: Recorder) -> tuple[Config, list[tuple]]:
    config = load_config(None)
    config.server.storage_root = STORAGE_DIR
    recorder.record_toggle("auth.mode", config.auth.mode, "pseudo")
    config.auth.mode = "pseudo"
    recorder.record_toggle(
        "feature_flags.overrides_enabled", config.feature_flags.overrides_enabled, True
    )
    config.feature_flags.overrides_enabled = True
    recorder.record_toggle("share.zip_attachments", config.share.zip_attachments, False)
    config.share.zip_attachments = False
    module_name, sent_emails = _install_email_sink()
    recorder.record_toggle("email.adapter", config.email.adapter, f"{module_name}:send_email")
    config.email.adapter = f"{module_name}:send_email"
    return config, sent_emails


def main() -> None:
    recorder = Recorder()
    _reset_workspace()
    _seed_routes()
    config, sent_emails = _configure(recorder)

    try:
        compile_routes(SRC_DIR, BUILD_DIR)
        routes = load_compiled_routes(BUILD_DIR)
        app = create_app(routes, config)
        client = TestClient(app)
        runner = LocalRouteRunner(routes=routes, config=config)

        login_payload = {"email": "workflow.demo@example.com"}
        login_response = client.post("/auth/pseudo/session", json=login_payload)
        login_response.raise_for_status()
        recorder.add_step(
            title="Create pseudo session",
            command="client.post(\"/auth/pseudo/session\", json=login_payload)",
            request=login_payload,
            response=login_response.json(),
        )

        schema_response = client.get("/routes/hello_world/schema")
        schema_response.raise_for_status()
        schema_data = schema_response.json()
        recorder.add_step(
            title="Inspect route schema and auto-form metadata",
            command="client.get(\"/routes/hello_world/schema\")",
            response=schema_data,
            notes=["Highlights auto-generated filters and override metadata."],
        )

        row_key = compute_row_key_from_values(
            {"greeting": "Hello, Workflow Demo!"}, ["greeting"]
        )
        override_payload = {
            "column": "note",
            "key": {"greeting": "Hello, Workflow Demo!"},
            "value": "Workflow override captured by generate_demo.py",
            "reason": "Pre-share annotation",
            "author": "workflow.demo@example.com",
        }
        override_response = client.post("/routes/hello_world/overrides", json=override_payload)
        override_response.raise_for_status()
        recorder.add_step(
            title="Submit override for the greeting row",
            command="client.post(\"/routes/hello_world/overrides\", json=override_payload)",
            request={"column": "note", "row_key": row_key, **override_payload},
            response=override_response.json(),
            notes=[
                "Row key computed via `compute_row_key_from_values`.",
                f"Recorded author hash proves provenance.",
            ],
        )

        runner_rows = runner.run(
            "hello_world", params={"name": "Workflow Demo"}, format="records"
        )
        runner_payload = {"rows": runner_rows}
        recorder.add_step(
            title="LocalRouteRunner view after override",
            command="runner.run(\"hello_world\", params={\"name\": \"Workflow Demo\"}, format=\"records\")",
            response=runner_payload,
            notes=[
                "Local execution picks up the override without HTTP.",
                "Note column reflects the annotated value.",
            ],
        )

        share_payload = {
            "emails": ["stakeholder@example.com"],
            "params": {"name": "Workflow Demo"},
            "format": "html_t",
            "attachments": ["csv", "html"],
            "inline_snapshot": True,
            "watermark": True,
        }
        share_response = client.post("/routes/hello_world/share", json=share_payload)
        share_response.raise_for_status()
        share_data = share_response.json()["share"]
        recorder.add_step(
            title="Create share with inline snapshot and attachments",
            command="client.post(\"/routes/hello_world/share\", json=share_payload)",
            request=share_payload,
            response=share_response.json(),
            notes=[
                f"Share token: {share_data['token']}",
                f"Attachments returned: {share_data['attachments']}",
                f"Rows shared: {share_data['rows_shared']}",
            ],
        )

        if sent_emails:
            recipients, subject, html_body, _text_body, attachments = sent_emails[-1]
            email_payload = {
                "to": list(recipients),
                "subject": subject,
                "attachments": [name for name, _ in attachments] if attachments else [],
                "html_excerpt": html_body[:200] + ("…" if len(html_body) > 200 else ""),
            }
            recorder.add_step(
                title="Captured outbound share email",
                command="sent_emails[-1]",
                response=email_payload,
                notes=["Stub adapter captures the audience and attachment filenames."],
            )

        share_token = share_data["token"]
        delivered_response = client.get(f"/shares/{share_token}?format=json")
        delivered_response.raise_for_status()
        delivered_payload = delivered_response.json()
        recorder.add_step(
            title="Fetch delivered share payload",
            command="client.get(f\"/shares/{share_token}?format=json\")",
            response=delivered_payload,
            notes=["Override survives into the shared rows."],
        )

        DEMO_PATH.write_text(
            recorder.to_markdown(generated_at=datetime.now(timezone.utc)), encoding="utf-8"
        )
    finally:
        shutil.rmtree(WORKSPACE_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
