"""Automation for the parameter forms demo.

This script launches the FastAPI app in-process, records responses for
multiple parameter combinations, captures metadata, and rebuilds
``demo.md`` so the documentation reflects the latest behaviour.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from typing import Any


DEMO_DIR = Path(__file__).resolve().parent
REPO_ROOT = DEMO_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from webbed_duck.cli import main as cli_main
from webbed_duck.config import load_config
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app

TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"
)
SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
RPC_RE = re.compile(
    r"<script[^>]+id=['\"]wd-rpc-config['\"][^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE
)


@dataclass
class CapturePaths:
    label: str
    title: str
    html_with_js: Path
    html_no_js: Path
    json_payload: Path
    form_summary: Path
    rpc_payload: Path
    pagination: Path


class ParamFormParser(HTMLParser):
    """Extract a lightweight summary of the parameter form."""

    def __init__(self) -> None:
        super().__init__()
        self.fields: list[dict[str, Any]] = []
        self._in_field = False
        self._field_depth = 0
        self._current: dict[str, Any] | None = None
        self._capture_label = False
        self._label_parts: list[str] = []
        self._in_select = False
        self._capture_option = False
        self._current_option: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name: (value or "") for name, value in attrs}
        if tag == "div":
            class_attr = attr_map.get("class", "")
            classes = {part.strip() for part in class_attr.split() if part.strip()}
            if not self._in_field and "param-field" in classes:
                self._in_field = True
                self._field_depth = 1
                self._current = {
                    "label": "",
                    "inputs": [],
                    "select": None,
                }
                return
            if self._in_field:
                self._field_depth += 1
        if not self._in_field or self._current is None:
            return
        if tag == "label":
            if self._current.get("_has_label"):
                return
            self._capture_label = True
            self._label_parts = []
        elif tag == "input":
            input_type = attr_map.get("type", "text").lower()
            if input_type in {"hidden", "checkbox", "search"}:
                return
            name = attr_map.get("name")
            if not name:
                return
            self._current["inputs"].append(
                {
                    "name": name,
                    "type": input_type,
                    "value": attr_map.get("value", ""),
                }
            )
        elif tag == "select":
            name = attr_map.get("name")
            if not name:
                return
            self._current["select"] = {
                "name": name,
                "multiple": "multiple" in attr_map,
                "placeholder": attr_map.get("data-placeholder", ""),
                "options": [],
            }
            self._in_select = True
        elif tag == "option" and self._in_select and self._current.get("select"):
            option = {
                "value": attr_map.get("value", ""),
                "label": "",
                "selected": "selected" in attr_map,
            }
            self._current_option = option
            self._capture_option = True

    def handle_data(self, data: str) -> None:
        if self._capture_label:
            self._label_parts.append(data)
        elif self._capture_option and self._current_option is not None:
            self._current_option["label"] += data

    def handle_endtag(self, tag: str) -> None:
        if self._capture_label and tag == "label":
            self._capture_label = False
            if self._current is not None:
                label = "".join(self._label_parts).strip()
                self._current["label"] = " ".join(label.split())
                self._current["_has_label"] = True
            self._label_parts = []
        elif self._capture_option and tag == "option":
            self._capture_option = False
            if self._current is not None and self._current_option is not None:
                option = dict(self._current_option)
                option["label"] = option["label"].strip()
                select = self._current.get("select")
                if select is not None:
                    select["options"].append(option)
            self._current_option = None
        elif tag == "select" and self._in_select:
            self._in_select = False
        elif tag == "div" and self._in_field:
            self._field_depth -= 1
            if self._field_depth <= 0:
                self._finalize_field()
                self._in_field = False
                self._field_depth = 0
                self._current = None

    def _finalize_field(self) -> None:
        if not self._current:
            return
        label = self._current.get("label", "")
        select = self._current.get("select")
        inputs = [entry for entry in self._current.get("inputs", []) if entry["type"] != "hidden"]
        summary: dict[str, Any] = {"label": label}
        if select:
            summary.update(
                {
                    "control": "select",
                    "name": select.get("name"),
                    "multiple": bool(select.get("multiple")),
                    "placeholder": select.get("placeholder", ""),
                    "options": [
                        {
                            "value": opt.get("value", ""),
                            "label": opt.get("label", ""),
                            "selected": bool(opt.get("selected")),
                        }
                        for opt in select.get("options", [])
                    ],
                }
            )
        elif inputs:
            primary = inputs[0]
            summary.update(
                {
                    "control": "input",
                    "name": primary.get("name"),
                    "type": primary.get("type", "text"),
                    "value": primary.get("value", ""),
                }
            )
        else:
            summary["control"] = "unsupported"
        self.fields.append(summary)


def sanitize_string(value: str) -> str:
    if not value:
        return value
    text = TIMESTAMP_RE.sub("<TIMESTAMP>", value)
    return text.replace("http://testserver", "http://demo-server")


def sanitize_html(text: str) -> str:
    return sanitize_string(text)


def sanitize_json_obj(obj: Any) -> Any:
    if isinstance(obj, dict):
        sanitized: dict[str, Any] = {}
        for key in sorted(obj):
            value = obj[key]
            if key in {"elapsed_ms", "average_ms", "p95_ms"} and isinstance(value, (int, float)):
                sanitized[key] = "<MS>"
            else:
                sanitized[key] = sanitize_json_obj(value)
        return sanitized
    if isinstance(obj, list):
        return [sanitize_json_obj(item) for item in obj]
    if isinstance(obj, str):
        return sanitize_string(obj)
    return obj


def strip_scripts(html: str) -> str:
    return SCRIPT_RE.sub("", html)


def extract_rpc_payload(html: str) -> dict[str, Any]:
    match = RPC_RE.search(html)
    if not match:
        return {}
    payload_text = match.group(1)
    try:
        return json.loads(payload_text)
    except json.JSONDecodeError:
        return {}


def parse_form_summary(html: str) -> dict[str, Any]:
    parser = ParamFormParser()
    parser.feed(html)
    return {"fields": parser.fields}


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def log_request(
    network_log: list[dict[str, Any]],
    *,
    label: str,
    method: str,
    path: str,
    params: dict[str, Any] | None,
    status: int,
    headers: dict[str, str],
    body_path: Path | None,
) -> None:
    body_reference: str | None
    if body_path is None:
        body_reference = None
    else:
        try:
            body_reference = str(body_path.relative_to(DEMO_DIR))
        except ValueError:
            body_reference = str(body_path)
    network_log.append(
        {
            "label": label,
            "request": {
                "method": method,
                "path": path,
                "params": params or {},
            },
            "response": {
                "status": status,
                "headers": headers,
                "body": body_reference,
            },
        }
    )


def run_cli_perf(repo_root: Path) -> str:
    args = [
        "perf",
        "hello_world",
        "--build",
        str(repo_root / "routes_build"),
        "--config",
        str(repo_root / "config.toml"),
        "--iterations",
        "1",
        "--param",
        "name=Swan",
        "--param",
        "greeting_length=12",
    ]
    buffer = StringIO()
    with redirect_stdout(buffer):
        cli_main(args)
    output = buffer.getvalue()
    output = re.sub(r"(Average latency: )[0-9.]+ ms", r"\1<MS> ms", output)
    output = re.sub(r"(95th percentile latency: )[0-9.]+ ms", r"\1<MS> ms", output)
    return output


def build_markdown(
    demo_dir: Path,
    captures: list[tuple[CapturePaths, dict[str, Any]]],
    metadata_summary: dict[str, Any],
    schema_path: Path,
    network_log_path: Path,
    cli_output_path: Path,
) -> str:
    lines: list[str] = []
    lines.append("# Parameter forms & progressive UI")
    lines.append("")
    lines.append("Generated by [`generate_demo.py`](generate_demo.py). The assets below are regenerated from live responses.")
    lines.append("")
    lines.append("## Route metadata")
    lines.append("")
    lines.append("* Route ID: `{route_id}`".format(route_id=metadata_summary.get("route_id")))
    lines.append("* Path: `{path}`".format(path=metadata_summary.get("path")))
    show_params = metadata_summary.get("show_params", {})
    if show_params:
        lines.append("* Show params: ``{}``".format(", ".join(
            f"{key}={values}" for key, values in show_params.items()
        )))
    cache_meta = metadata_summary.get("cache", {})
    if cache_meta:
        lines.append("* Cache metadata: ``{}``".format(cache_meta))
    lines.append("")
    lines.append(f"See the compiled schema snapshot in [`{schema_path.relative_to(demo_dir)}`](" +
                 f"{schema_path.relative_to(demo_dir)}) for column details.")
    lines.append("")
    lines.append("## Captured parameter sets")
    lines.append("")
    for capture, summary in captures:
        lines.append(f"### {capture.title}")
        lines.append("")
        query_items = summary.get("query") or {}
        if query_items:
            query_repr = "&".join(f"{key}={value}" for key, value in query_items.items())
            lines.append(f"* **Request:** `GET /hello?{query_repr}`")
        else:
            lines.append("* **Request:** `GET /hello` (defaults)")
        lines.append(
            "* **HTML (progressive markup):** "
            f"[`{capture.html_with_js.name}`](artifacts/{capture.html_with_js.name})"
        )
        lines.append(
            "* **HTML (scripts removed):** "
            f"[`{capture.html_no_js.name}`](artifacts/{capture.html_no_js.name})"
        )
        lines.append(
            "* **JSON payload:** "
            f"[`{capture.json_payload.name}`](artifacts/{capture.json_payload.name})"
        )
        lines.append(
            "* **Form summary:** "
            f"[`{capture.form_summary.name}`](artifacts/{capture.form_summary.name})"
        )
        lines.append(
            "* **RPC payload:** "
            f"[`{capture.rpc_payload.name}`](artifacts/{capture.rpc_payload.name})"
        )
        lines.append(
            "* **Pagination trace (limit=1):** "
            f"[`{capture.pagination.name}`](artifacts/{capture.pagination.name})"
        )
        fields = summary.get("form_fields", [])
        if fields:
            lines.append("")
            lines.append("  Parameter controls:")
            for field in fields:
                if field.get("control") == "input":
                    lines.append(
                        "  * `{label}` → `{type}` input (value `{value}`)".format(
                            label=field.get("label"),
                            type=field.get("type"),
                            value=field.get("value"),
                        )
                    )
                elif field.get("control") == "select":
                    option_labels = [opt.get("label") or opt.get("value") for opt in field.get("options", [])]
                    lines.append(
                        "  * `{label}` → multi-select options {options}".format(
                            label=field.get("label"),
                            options=option_labels,
                        )
                    )
        lines.append("")
    lines.append("## CLI verification")
    lines.append("")
    lines.append("* Command: `webbed-duck perf hello_world --iterations 1 --param name=Swan --param greeting_length=12`")
    lines.append(
        "* Output: [`{}`](artifacts/{})".format(
            cli_output_path.name,
            cli_output_path.name,
        )
    )
    lines.append("")
    lines.append("## Network log")
    lines.append("")
    lines.append(
        "All recorded requests are listed in [`{}`](artifacts/{}).".format(
            network_log_path.name,
            network_log_path.name,
        )
    )
    lines.append("")
    lines.append(
        "Timestamps and hostnames are normalised to keep the artefacts deterministic "
        "(dynamic values render as `<TIMESTAMP>` and `http://demo-server`)."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    demo_dir = Path(__file__).resolve().parent
    repo_root = REPO_ROOT
    artifact_dir = demo_dir / "artifacts"
    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    config = load_config(repo_root / "config.toml")
    routes = load_compiled_routes(repo_root / config.server.build_dir)
    app = create_app(routes, config)

    storage_root = (repo_root / config.server.storage_root).resolve()
    cache_dir = storage_root / "cache"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    route = next(route for route in routes if route.path == "/hello")
    metadata_summary = {
        "route_id": route.id,
        "path": route.path,
        "show_params": {
            key: route.metadata.get(key, {}).get("show_params", [])
            for key in ("html_t", "html_c")
            if isinstance(route.metadata.get(key), dict)
        },
        "cache": route.metadata.get("cache", {}),
    }

    parameter_cases = [
        {"label": "default", "title": "Default parameters", "params": {}},
        {"label": "swan", "title": "Custom name (name=Swan)", "params": {"name": "Swan"}},
        {
            "label": "swan_filtered",
            "title": "Swan filtered by greeting length",
            "params": {"name": "Swan", "greeting_length": "12"},
        },
    ]

    captures: list[tuple[CapturePaths, dict[str, Any]]] = []
    network_log: list[dict[str, Any]] = []

    with TestClient(app) as client:
        for case in parameter_cases:
            label = case["label"]
            base_params = {key: value for key, value in case["params"].items()}
            html_params = {**base_params, "format": "html_t"}
            html_response = client.get("/hello", params=html_params)
            sanitized_html = sanitize_html(html_response.text)
            html_with_js_path = artifact_dir / f"{label}_hello_with_js.html"
            html_with_js_path.write_text(sanitized_html, encoding="utf-8")
            rpc_payload = sanitize_json_obj(extract_rpc_payload(html_response.text))
            rpc_path = artifact_dir / f"{label}_rpc.json"
            write_json(rpc_path, rpc_payload)
            no_js_html = strip_scripts(sanitized_html)
            html_no_js_path = artifact_dir / f"{label}_hello_no_js.html"
            html_no_js_path.write_text(no_js_html, encoding="utf-8")
            form_summary = parse_form_summary(no_js_html)
            form_path = artifact_dir / f"{label}_form.json"
            write_json(form_path, form_summary)
            log_request(
                network_log,
                label=f"{label}_html",
                method="GET",
                path="/hello",
                params=html_params,
                status=html_response.status_code,
                headers={
                    key: sanitize_string(html_response.headers.get(key, ""))
                    for key in ("content-type", "x-total-rows", "x-limit", "x-offset")
                },
                body_path=html_with_js_path,
            )

            json_response = client.get("/hello", params={**base_params, "format": "json"})
            sanitized_json = sanitize_json_obj(json_response.json())
            json_path = artifact_dir / f"{label}_hello.json"
            write_json(json_path, sanitized_json)
            log_request(
                network_log,
                label=f"{label}_json",
                method="GET",
                path="/hello",
                params={**base_params, "format": "json"},
                status=json_response.status_code,
                headers={"content-type": json_response.headers.get("content-type", "")},
                body_path=json_path,
            )

            pagination_params = {**base_params, "format": "html_t", "limit": 1}
            pagination_response = client.get("/hello", params=pagination_params)
            pagination_headers = {
                key: sanitize_string(pagination_response.headers.get(key, ""))
                for key in ("content-type", "x-total-rows", "x-limit", "x-offset")
            }
            pagination_rpc = sanitize_json_obj(extract_rpc_payload(pagination_response.text))
            pagination_path = artifact_dir / f"{label}_pagination.json"
            write_json(
                pagination_path,
                {
                    "headers": pagination_headers,
                    "rpc": pagination_rpc,
                },
            )
            log_request(
                network_log,
                label=f"{label}_pagination",
                method="GET",
                path="/hello",
                params=pagination_params,
                status=pagination_response.status_code,
                headers=pagination_headers,
                body_path=pagination_path,
            )

            capture_paths = CapturePaths(
                label=label,
                title=case["title"],
                html_with_js=html_with_js_path,
                html_no_js=html_no_js_path,
                json_payload=json_path,
                form_summary=form_path,
                rpc_payload=rpc_path,
                pagination=pagination_path,
            )
            captures.append(
                (
                    capture_paths,
                    {
                        "query": base_params,
                        "form_fields": form_summary.get("fields", []),
                    },
                )
            )

        schema_response = client.get("/routes/hello_world/schema")
        schema_path = artifact_dir / "hello_schema.json"
        write_json(schema_path, sanitize_json_obj(schema_response.json()))
        log_request(
            network_log,
            label="schema",
            method="GET",
            path="/routes/hello_world/schema",
            params={},
            status=schema_response.status_code,
            headers={"content-type": schema_response.headers.get("content-type", "")},
            body_path=schema_path,
        )

    network_log_path = artifact_dir / "network_log.json"
    write_json(network_log_path, network_log)

    cli_output = run_cli_perf(repo_root)
    cli_output_path = artifact_dir / "cli_perf.txt"
    cli_output_path.write_text(cli_output, encoding="utf-8")

    metadata_path = artifact_dir / "route_metadata.json"
    write_json(metadata_path, sanitize_json_obj(metadata_summary))

    demo_markdown = build_markdown(
        demo_dir,
        captures,
        metadata_summary,
        schema_path,
        network_log_path,
        cli_output_path,
    )
    (demo_dir / "demo.md").write_text(demo_markdown + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
