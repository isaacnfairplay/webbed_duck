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

from fastapi.testclient import TestClient  # noqa: E402

from webbed_duck.config import Config, load_config  # noqa: E402
from webbed_duck.core.compiler import compile_routes  # noqa: E402
from webbed_duck.core.local import LocalRouteRunner  # noqa: E402
from webbed_duck.core.routes import load_compiled_routes  # noqa: E402
from webbed_duck.server.app import create_app  # noqa: E402
from webbed_duck.server.overlay import compute_row_key_from_values  # noqa: E402

DEMO_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = DEMO_DIR / "_workspace"
SRC_DIR = WORKSPACE_DIR / "routes_src"
BUILD_DIR = WORKSPACE_DIR / "routes_build"
STORAGE_DIR = WORKSPACE_DIR / "storage"
DEMO_PATH = DEMO_DIR / "demo.md"
ROUTE_SOURCE = Path("routes_src")


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


@dataclass(slots=True)
class DemoEntry:
    title: str
    command: str
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


@dataclass(slots=True)
class DemoRecorder:
    title: str
    entries: list[DemoEntry] = field(default_factory=list)
    toggles: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add(self, entry: DemoEntry) -> None:
        self.entries.append(entry)

    def set_toggle(self, name: str, before: Any, after: Any) -> None:
        self.toggles[name] = {"before": before, "after": after}

    def to_markdown(self, *, generated_at: datetime) -> str:
        lines: list[str] = []
        lines.append("<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->")
        lines.append(f"# {self.title}")
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
        return "\n".join(lines).strip() + "\n"


@contextmanager
def toggled_config(config: Config, *, overrides_enabled: bool, auth_mode: str) -> Iterator[dict[str, Any]]:
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


def _serialize_records(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        return {"rows": data}
    return {"result": data}


def generate_demo() -> None:
    recorder = DemoRecorder(title="Insight Synergy Demo")
    _reset_workspace()
    _seed_routes()

    compiled = compile_routes(SRC_DIR, BUILD_DIR)
    recorder.add(
        DemoEntry(
            title="Compile hello route",
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
            else:
                after = getattr(config, name, None)
            recorder.set_toggle(name, before=before, after=after)

        runner = LocalRouteRunner(routes=routes, config=config)
        preview_rows = runner.run(
            route_id="hello_world",
            params={"name": "Synergy"},
            format="records",
        )
        recorder.add(
            DemoEntry(
                title="Local preview before overrides",
                command="runner.run(route_id=\"hello_world\", params={\"name\": \"Synergy\"}, format=\"records\")",
                response=_serialize_records(preview_rows),
            )
        )

        first_row = preview_rows[0] if isinstance(preview_rows, list) and preview_rows else {}
        row_key = compute_row_key_from_values({"greeting": first_row.get("greeting", "")}, ["greeting"])

        app = create_app(routes, config)
        client = TestClient(app)

        login_payload = {"email": "analyst@example.com", "display_name": "Insight Builder"}
        login_response = client.post("/auth/pseudo/session", json=login_payload)
        recorder.add(
            DemoEntry(
                title="Create pseudo session",
                command="client.post(\"/auth/pseudo/session\", json=login_payload)",
                request=login_payload,
                response=login_response.json(),
                meta={"status_code": login_response.status_code},
            )
        )

        schema_response = client.get("/routes/hello_world/schema", params={"name": "Synergy"})
        recorder.add(
            DemoEntry(
                title="Inspect auto-generated form & schema",
                command='client.get("/routes/hello_world/schema", params={"name": "Synergy"})',
                response=schema_response.json(),
                meta={"status_code": schema_response.status_code},
            )
        )

        override_payload = {
            "row_key": row_key,
            "column": "note",
            "value": "Synergy preview curated via override",
            "reason": "Blend local preview with overlays before sharing",
            "author": "Insight Builder",
        }
        override_response = client.post("/routes/hello_world/overrides", json=override_payload)
        recorder.add(
            DemoEntry(
                title="Apply override through HTTP",
                command='client.post("/routes/hello_world/overrides", json=override_payload)',
                request=override_payload,
                response=override_response.json(),
                meta={"status_code": override_response.status_code},
            )
        )

        curated_rows = runner.run(
            route_id="hello_world",
            params={"name": "Synergy"},
            format="records",
        )
        recorder.add(
            DemoEntry(
                title="Local preview after override",
                command="runner.run(route_id=\"hello_world\", params={\"name\": \"Synergy\"}, format=\"records\")",
                response=_serialize_records(curated_rows),
            )
        )

        local_payload = {
            "reference": "local:hello_world?column=greeting&column=note&column=created_at",
            "params": {"name": "Synergy"},
            "format": "json",
            "record_analytics": True,
        }
        local_response = client.post("/local/resolve", json=local_payload)
        recorder.add(
            DemoEntry(
                title="Resolve local reference with analytics",
                command='client.post("/local/resolve", json=local_payload)',
                request=local_payload,
                response=local_response.json(),
                meta={"status_code": local_response.status_code},
            )
        )

        share_payload = {
            "emails": ["surprise@stakeholders.local"],
            "params": {"name": "Synergy"},
            "format": "json",
            "columns": ["greeting", "note", "created_at"],
            "attachments": ["csv", "html"],
            "watermark_text": "Synergy share watermark",
            "zip": True,
            "zip_passphrase": "synergy-demo",
        }
        share_response = client.post("/routes/hello_world/share", json=share_payload)
        share_json = share_response.json()
        recorder.add(
            DemoEntry(
                title="Create curated share with attachments",
                command='client.post("/routes/hello_world/share", json=share_payload)',
                request=share_payload,
                response=share_json,
                meta={"status_code": share_response.status_code},
            )
        )

        share_token = share_json.get("share", {}).get("token")
        if share_token:
            share_resolve = client.get(f"/shares/{share_token}?format=json")
            recorder.add(
                DemoEntry(
                    title="Resolve share token to confirm payload",
                    command=f'client.get("/shares/{share_token}?format=json")',
                    response=share_resolve.json(),
                    meta={"status_code": share_resolve.status_code},
                )
            )

        routes_response = client.get("/routes")
        recorder.add(
            DemoEntry(
                title="Inspect route listing with analytics",
                command='client.get("/routes")',
                response=routes_response.json(),
                meta={"status_code": routes_response.status_code},
            )
        )

    shutil.rmtree(WORKSPACE_DIR, ignore_errors=True)

    generated_at = datetime.now(timezone.utc)
    DEMO_PATH.write_text(recorder.to_markdown(generated_at=generated_at), encoding="utf-8")


if __name__ == "__main__":
    generate_demo()
