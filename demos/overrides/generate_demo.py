"""Generate the overrides demo documentation and capture artifacts.

This script spins up an in-process FastAPI application using the compiled
``hello_world`` route, issues live HTTP requests against the override
endpoints, collects the rendered HTML evidence, and persists the raw traffic in
``captures/``. A Markdown walkthrough (``demo.md``) is rebuilt on every run
using those captures so the narrative always matches the actual behaviour.

Run with ``python demos/overrides/generate_demo.py`` from the repository root.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import sys
import textwrap
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from webbed_duck.config import load_config
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app
from webbed_duck.server.overlay import compute_row_key_from_values


@dataclass(slots=True)
class StepCapture:
    """Container describing a single recorded HTTP interaction."""

    name: str
    title: str
    description: str
    request_file: Path
    response_file: Path
    request_text: str
    response_text: str
    response_json: Any | None = None
    html_file: Path | None = None
    html_snippet: str | None = None


def _prepare_directories(root: Path) -> tuple[Path, Path, Path]:
    """Clear and recreate capture directories under ``root``."""

    if root.exists():
        shutil.rmtree(root)
    http_dir = root / "http"
    html_dir = root / "html"
    storage_root = root / "storage"
    http_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)
    storage_root.mkdir(parents=True, exist_ok=True)
    return http_dir, html_dir, storage_root


def _format_request(prepared_request) -> str:
    """Return a raw HTTP-style representation of the outgoing request."""

    method = prepared_request.method
    split = urlsplit(str(prepared_request.url))
    path = split.path or "/"
    if split.query:
        path = f"{path}?{split.query}"
    request_line = f"{method} {path} HTTP/1.1"

    headers_map = dict(prepared_request.headers or {})
    if "host" not in {key.lower() for key in headers_map} and split.netloc:
        headers_map["Host"] = split.netloc
    header_lines = [f"{key}: {value}" for key, value in sorted(headers_map.items(), key=lambda item: item[0].lower())]
    body = getattr(prepared_request, "body", None)
    if body is None:
        body = getattr(prepared_request, "content", None)
    if body:
        if isinstance(body, bytes):
            body_text = body.decode("utf-8", "replace")
        else:
            body_text = str(body)
        return "\n".join([request_line, *header_lines, "", body_text])
    return "\n".join([request_line, *header_lines])


def _format_response(response) -> str:
    """Return a raw HTTP-style representation of ``response``."""

    reason = getattr(response, "reason", None) or getattr(response, "reason_phrase", "")
    status_line = f"HTTP/1.1 {response.status_code} {reason}".rstrip()
    header_lines = [f"{key}: {value}" for key, value in sorted(response.headers.items(), key=lambda item: item[0].lower())]
    content = response.content
    if content:
        body = content.decode("utf-8", "replace")
        return "\n".join([status_line, *header_lines, "", body])
    return "\n".join([status_line, *header_lines])


def _capture_http(
    index: int,
    name: str,
    title: str,
    description: str,
    response,
    *,
    http_dir: Path,
    html_dir: Path,
    capture_html: bool = False,
) -> StepCapture:
    """Persist request/response payloads and return a :class:`StepCapture`."""

    prepared = response.request
    request_text = _format_request(prepared)
    response_text = _format_response(response)

    request_file = http_dir / f"{index:02d}_{name}_request.http"
    response_file = http_dir / f"{index:02d}_{name}_response.http"
    request_file.write_text(request_text, encoding="utf-8")
    response_file.write_text(response_text, encoding="utf-8")

    response_json: Any | None = None
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            response_json = response.json()
        except ValueError:
            response_json = None

    html_file: Path | None = None
    html_snippet: str | None = None
    if capture_html:
        html_file = html_dir / f"{index:02d}_{name}.html"
        html_file.write_text(response.text, encoding="utf-8")
        html_snippet = _extract_note_cell(response.text)

    return StepCapture(
        name=name,
        title=title,
        description=description,
        request_file=request_file,
        response_file=response_file,
        request_text=request_text,
        response_text=response_text,
        response_json=response_json,
        html_file=html_file,
        html_snippet=html_snippet,
    )


def _extract_note_cell(html_text: str) -> str | None:
    """Return the `<td>` for the `note` column when present."""

    match = re.search(r"(<td[^>]*class=\"[^\"]*note[^\"]*\"[^>]*>.*?</td>)", html_text, re.IGNORECASE | re.DOTALL)
    snippet: str | None
    if match:
        snippet = match.group(1)
    else:
        snippet = None
        tbody_match = re.search(r"<tbody>(.*?)</tbody>", html_text, re.IGNORECASE | re.DOTALL)
        if tbody_match:
            row_match = re.search(r"<tr>(.*?)</tr>", tbody_match.group(1), re.IGNORECASE | re.DOTALL)
            if row_match:
                cells = re.findall(r"<td.*?</td>", row_match.group(1), re.IGNORECASE | re.DOTALL)
                if len(cells) >= 2:
                    snippet = cells[1]
    if not snippet:
        return None
    cleaned = unescape(snippet.strip())
    return textwrap.dedent(cleaned)


def _build_markdown(
    steps: list[StepCapture],
    teardown_info: Mapping[str, Any],
    *,
    output_path: Path,
    scenario_summary: str,
) -> None:
    """Render ``demo.md`` from the captured steps."""

    timestamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = []
    lines.append("# Overrides demo")
    lines.append("")
    lines.append(f"_Generated by `generate_demo.py` on {timestamp}._")
    lines.append("")
    lines.append(scenario_summary)
    lines.append("")
    lines.append("Run `python demos/overrides/generate_demo.py` to refresh the captures and this document.")
    lines.append("")

    for idx, step in enumerate(steps, start=1):
        lines.append(f"## Step {idx}: {step.title}")
        lines.append("")
        lines.append(step.description)
        lines.append("")
        lines.append("### Raw request")
        lines.append("```http")
        lines.append(step.request_text)
        lines.append("```")
        lines.append("")
        lines.append("### Raw response")
        lines.append("```http")
        lines.append(step.response_text)
        lines.append("```")
        lines.append("")
        if step.response_json is not None:
            lines.append("### JSON payload")
            lines.append("```json")
            lines.append(json.dumps(step.response_json, indent=2, sort_keys=True))
            lines.append("```")
            lines.append("")
        if step.html_snippet:
            lines.append("### HTML evidence")
            lines.append("```html")
            lines.append(step.html_snippet)
            lines.append("```")
            lines.append("")
        request_rel = step.request_file.name
        response_rel = step.response_file.name
        artifacts = [f"[`http/{request_rel}`](./captures/http/{request_rel})", f"[`http/{response_rel}`](./captures/http/{response_rel})"]
        if step.html_file is not None:
            artifacts.append(f"[`html/{step.html_file.name}`](./captures/html/{step.html_file.name})")
        lines.append("Artifacts: " + ", ".join(artifacts))
        lines.append("")

    lines.append("## Teardown")
    lines.append("")
    lines.append("Overrides created during the run are removed to keep subsequent executions clean.")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(dict(teardown_info), indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("The final override audit (see the last step above) verifies the store is empty.")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent

    captures_root = script_dir / "captures"
    http_dir, html_dir, storage_root = _prepare_directories(captures_root)

    routes = load_compiled_routes(repo_root / "routes_build")
    try:
        hello_route = next(route for route in routes if route.id == "hello_world")
    except StopIteration as exc:  # pragma: no cover - sanity guard
        raise RuntimeError("hello_world route is required for the overrides demo") from exc

    config = load_config(None)
    config.server.storage_root = storage_root
    config.feature_flags.overrides_enabled = True
    config.analytics.enabled = False

    app = create_app(routes, config)

    name_param = "Audit Demo"
    override_value = "Override note captured by generate_demo.py"
    override_reason = "Documenting manual note update"
    override_author = "demo.generator@company.local"
    overrides_meta: Mapping[str, Any] | None = None
    if isinstance(hello_route.metadata, Mapping):
        candidate = hello_route.metadata.get("overrides")
        if isinstance(candidate, Mapping):
            overrides_meta = candidate
    key_columns = overrides_meta.get("key_columns") if overrides_meta else None
    row_key = compute_row_key_from_values({"greeting": f"Hello, {name_param}!"}, key_columns)

    steps: list[StepCapture] = []

    teardown_info: Mapping[str, Any] = {}

    with TestClient(app) as client:
        response = client.get(
            hello_route.path,
            params={"format": "html_t", "name": name_param},
            headers={"accept": "text/html"},
        )
        steps.append(
            _capture_http(
                1,
                "initial_html",
                "Render the greeting before overrides",
                "Baseline HTML render of the `hello_world` route before any overrides are applied.",
                response,
                http_dir=http_dir,
                html_dir=html_dir,
                capture_html=True,
            )
        )

        override_payload = {
            "column": "note",
            "row_key": row_key,
            "value": override_value,
            "reason": override_reason,
            "author": override_author,
        }
        response = client.post(
            f"/routes/{hello_route.id}/overrides",
            json=override_payload,
        )
        steps.append(
            _capture_http(
                2,
                "create_override",
                "Submit an override for the note column",
                "POST the override payload documenting the new note and author metadata.",
                response,
                http_dir=http_dir,
                html_dir=html_dir,
            )
        )

        response = client.get(f"/routes/{hello_route.id}/overrides")
        steps.append(
            _capture_http(
                3,
                "audit_after_create",
                "Inspect the override audit trail",
                "Retrieve the overlay store entries after creating the override to surface the recorded author and reason.",
                response,
                http_dir=http_dir,
                html_dir=html_dir,
            )
        )

        response = client.get(
            hello_route.path,
            params={"format": "html_t", "name": name_param},
            headers={"accept": "text/html"},
        )
        steps.append(
            _capture_http(
                4,
                "html_after_override",
                "Render HTML with the override applied",
                "Confirm the rendered table shows the overridden note value.",
                response,
                http_dir=http_dir,
                html_dir=html_dir,
                capture_html=True,
            )
        )

        removed = client.app.state.overlays.remove(hello_route.id, row_key, "note")
        teardown_path = captures_root / "teardown.json"
        teardown_timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
        teardown_info = {
            "removed": removed,
            "route_id": hello_route.id,
            "row_key": row_key,
            "column": "note",
            "timestamp": teardown_timestamp,
        }
        teardown_path.write_text(json.dumps(teardown_info, indent=2, sort_keys=True), encoding="utf-8")

        response = client.get(f"/routes/{hello_route.id}/overrides")
        steps.append(
            _capture_http(
                5,
                "audit_after_teardown",
                "Verify overrides are cleared",
                "Confirm the overlay store no longer contains entries for the route after teardown.",
                response,
                http_dir=http_dir,
                html_dir=html_dir,
            )
        )

        response = client.get(
            hello_route.path,
            params={"format": "html_t", "name": name_param},
            headers={"accept": "text/html"},
        )
        steps.append(
            _capture_http(
                6,
                "html_post_teardown",
                "Render HTML after cleanup",
                "Final render showing the note has reverted to the base DuckDB value once the override is removed.",
                response,
                http_dir=http_dir,
                html_dir=html_dir,
                capture_html=True,
            )
        )

    scenario_summary = (
        "The automation seeds the `hello_world` route with a named greeting, "
        "applies a cell-level override via the HTTP API, captures audit details, "
        "and then rolls back the change so repeated runs start from a clean state."
    )

    _build_markdown(
        steps,
        teardown_info,
        output_path=script_dir / "demo.md",
        scenario_summary=scenario_summary,
    )


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()

