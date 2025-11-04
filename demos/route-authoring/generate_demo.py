from __future__ import annotations

import dataclasses
import html
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import List

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import httpx
import pyarrow as pa
import pyarrow.ipc as pa_ipc

try:
    from webbed_duck import __version__ as PACKAGE_VERSION
except Exception:  # pragma: no cover - import guard for local execution
    PACKAGE_VERSION = None


@dataclasses.dataclass(slots=True)
class CommandCapture:
    command: List[str]
    returncode: int
    stdout: str
    stderr: str
    duration_s: float


@dataclasses.dataclass(slots=True)
class ServerRun:
    command: List[str]
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    host: str
    port: int


@dataclasses.dataclass(slots=True)
class HttpCapture:
    label: str
    method: str
    url: str
    params: Mapping[str, str]
    status_code: int
    reason: str
    elapsed_ms: float
    headers: Mapping[str, str]
    body: bytes
    text: str | None = None
    arrow_table: pa.Table | None = None


@dataclasses.dataclass(slots=True)
class DirectorySnapshot:
    path: Path
    existed: bool
    _tempdir: tempfile.TemporaryDirectory[str]
    backup: Path | None

    @classmethod
    def create(cls, path: Path) -> "DirectorySnapshot":
        tempdir = tempfile.TemporaryDirectory(prefix="wd_demo_snapshot_")
        existed = path.exists()
        backup: Path | None = None
        if existed:
            backup = Path(tempdir.name) / "backup"
            shutil.copytree(path, backup)
        return cls(path=path, existed=existed, _tempdir=tempdir, backup=backup)

    def wipe(self, *, recreate: bool) -> None:
        if self.path.exists():
            shutil.rmtree(self.path)
        if recreate:
            self.path.mkdir(parents=True, exist_ok=True)

    def restore(self) -> None:
        if self.path.exists():
            shutil.rmtree(self.path)
        if self.existed and self.backup is not None:
            shutil.copytree(self.backup, self.path)

    def cleanup(self) -> None:
        self._tempdir.cleanup()


@dataclasses.dataclass(slots=True)
class DirectoryListing:
    root: Path
    files: list[tuple[Path, int]]


def _format_command(command: Sequence[str]) -> str:
    return " ".join(str(part) for part in command)


def run_command(command: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None = None) -> CommandCapture:
    start = time.perf_counter()
    completed = subprocess.run(
        list(command),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=dict(env) if env is not None else None,
    )
    duration = time.perf_counter() - start
    return CommandCapture(
        command=list(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_s=duration,
    )


def _consume_stream(stream, sink: list[str]) -> None:
    try:
        for line in iter(stream.readline, ""):
            sink.append(line)
    finally:
        try:
            stream.close()
        except Exception:
            pass


def launch_server(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    host: str,
    port: int,
) -> tuple[subprocess.Popen[str], list[str], list[str], threading.Thread, threading.Thread]:
    process = subprocess.Popen(
        list(command),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=dict(env),
    )
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    stdout_thread = threading.Thread(target=_consume_stream, args=(process.stdout, stdout_lines), daemon=True)
    stderr_thread = threading.Thread(target=_consume_stream, args=(process.stderr, stderr_lines), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    try:
        _wait_for_server(host, port, process)
    except Exception:
        stop_server(process)
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
        raise
    return process, stdout_lines, stderr_lines, stdout_thread, stderr_thread


def _wait_for_server(host: str, port: int, process: subprocess.Popen[str], timeout: float = 30.0) -> None:
    base_url = f"http://{host}:{port}"
    deadline = time.monotonic() + timeout
    with httpx.Client() as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Server exited with code {process.returncode} before becoming ready")
            try:
                response = client.get(f"{base_url}/routes", timeout=1.0)
            except httpx.RequestError:
                time.sleep(0.2)
                continue
            if response.status_code < 500:
                return
            time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for server at {base_url}")


def stop_server(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        process.send_signal(signal.SIGINT)
        process.wait(timeout=10)
    except (AttributeError, ValueError, ProcessLookupError):
        pass
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    finally:
        try:
            process.stdout.close()  # type: ignore[call-arg]
        except Exception:
            pass
        try:
            process.stderr.close()  # type: ignore[call-arg]
        except Exception:
            pass


def request_route(host: str, port: int, *, label: str, params: Mapping[str, str]) -> HttpCapture:
    base_url = f"http://{host}:{port}"
    url = f"{base_url}/hello"
    with httpx.Client() as client:
        start = time.perf_counter()
        response = client.get(url, params=params, timeout=10.0)
        elapsed_ms = (time.perf_counter() - start) * 1000
    body = response.content
    text_value: str | None = None
    arrow_table: pa.Table | None = None
    if response.headers.get("content-type", "").startswith("text/") or "html" in response.headers.get("content-type", ""):
        text_value = response.text
    elif response.headers.get("content-type", "").startswith("application/json"):
        text_value = response.text
    elif params.get("format", "").lower() == "arrow":
        reader = pa_ipc.RecordBatchStreamReader(pa.BufferReader(body))
        arrow_table = reader.read_all()
    return HttpCapture(
        label=label,
        method="GET",
        url=url,
        params=dict(params),
        status_code=response.status_code,
        reason=response.reason_phrase,
        elapsed_ms=elapsed_ms,
        headers=dict(response.headers),
        body=body,
        text=text_value,
        arrow_table=arrow_table,
    )


def collect_listing(path: Path) -> DirectoryListing:
    files: list[tuple[Path, int]] = []
    if not path.exists():
        return DirectoryListing(root=path, files=[])
    for item in sorted(path.rglob("*")):
        if item.is_file():
            try:
                size = item.stat().st_size
            except OSError:
                size = -1
            files.append((item.relative_to(path), size))
    return DirectoryListing(root=path, files=files)


def format_listing(listing: DirectoryListing) -> str:
    if not listing.files:
        return "(no files)"
    lines = ["| Path | Size (bytes) |", "| --- | ---: |"]
    for rel_path, size in listing.files:
        lines.append(f"| {rel_path.as_posix()} | {size} |")
    return "\n".join(lines)


def _format_stdout(stderr_or_stdout: str) -> str:
    if not stderr_or_stdout.strip():
        return "(empty)"
    return stderr_or_stdout.rstrip()


def _arrow_table_markdown(table: pa.Table) -> str:
    columns = list(table.column_names)
    if not columns:
        return "(empty table)"
    data = table.to_pydict()
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows: list[str] = []
    for index in range(table.num_rows):
        values = []
        for column in columns:
            col_values = data.get(column, [])
            value = col_values[index] if index < len(col_values) else None
            if isinstance(value, float):
                values.append(f"{value:.6g}")
            elif isinstance(value, datetime):
                values.append(value.isoformat())
            else:
                values.append(str(value))
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join([header, separator, *rows])


_SCRIPT_RE = re.compile(r"(?is)<script[^>]*?>.*?</script>")
_STYLE_RE = re.compile(r"(?is)<style[^>]*?>.*?</style>")


def _is_html_response(content_type: str, text: str | None) -> bool:
    if text is None:
        return False
    lowered = content_type.lower()
    if "html" in lowered:
        return True
    stripped = text.lstrip()
    return stripped.startswith("<!doctype html") or stripped.startswith("<html")


def _extract_body_html(raw_html: str) -> str | None:
    match = re.search(r"(?is)<body[^>]*>(.*)</body>", raw_html)
    fragment = match.group(1) if match else raw_html
    fragment = _SCRIPT_RE.sub("", fragment)
    fragment = _STYLE_RE.sub("", fragment)
    fragment = fragment.strip()
    return fragment or None


def _html_source_and_preview_blocks(raw_html: str, preview_label: str) -> list[str]:
    preview_html = _extract_body_html(raw_html)
    lines = [
        "<details>",
        "<summary>View HTML source</summary>",
        "",
        "```html",
        raw_html.rstrip(),
        "```",
        "",
        "</details>",
        "",
    ]
    if preview_html is not None:
        attr = html.escape(preview_label, quote=True)
        lines.append(f"<div class=\"demo-preview\" data-source=\"{attr}\">")
        lines.append(preview_html)
        lines.append("</div>")
    else:
        lines.append("_Rendered preview unavailable (response body missing)._")
    lines.append("")
    return lines


def generate_markdown(
    *,
    timestamp: datetime,
    compile_capture: CommandCapture,
    server_run: ServerRun,
    http_captures: Sequence[HttpCapture],
    build_listing: DirectoryListing,
    storage_listing: DirectoryListing,
) -> str:
    lines: list[str] = []
    lines.append("# Route Authoring & Serving Demo")
    lines.append("")
    lines.append(f"_Auto-generated on {timestamp.isoformat()}Z_")
    lines.append("")
    lines.append("## Environment")
    lines.append("")
    lines.append(f"- Python: {sys.version.splitlines()[0]}")
    if PACKAGE_VERSION is not None:
        lines.append(f"- webbed_duck version: {PACKAGE_VERSION}")
    else:
        lines.append("- webbed_duck version: (unavailable)")
    lines.append("")
    lines.append("## Compile step")
    lines.append("")
    lines.append(f"Command: `{_format_command(compile_capture.command)}`")
    lines.append("")
    lines.append(f"Return code: {compile_capture.returncode}")
    lines.append("")
    lines.append(f"Duration: {compile_capture.duration_s:.2f} s")
    lines.append("")
    lines.append("### stdout")
    lines.append("")
    lines.append("```\n" + _format_stdout(compile_capture.stdout) + "\n```")
    lines.append("")
    lines.append("### stderr")
    lines.append("")
    lines.append("```\n" + _format_stdout(compile_capture.stderr) + "\n```")
    lines.append("")
    lines.append("## Serve step")
    lines.append("")
    lines.append(f"Command: `{_format_command(server_run.command)}`")
    lines.append("")
    lines.append(f"Return code: {server_run.returncode}")
    lines.append("")
    lines.append(f"Duration: {server_run.duration_s:.2f} s")
    lines.append("")
    lines.append("### stdout")
    lines.append("")
    lines.append("```\n" + _format_stdout(server_run.stdout) + "\n```")
    lines.append("")
    lines.append("### stderr")
    lines.append("")
    lines.append("```\n" + _format_stdout(server_run.stderr) + "\n```")
    lines.append("")
    lines.append("## HTTP walkthrough")
    lines.append("")
    for capture in http_captures:
        lines.append(f"### {capture.label}")
        lines.append("")
        query = "&".join(f"{key}={value}" for key, value in capture.params.items())
        lines.append(f"`{capture.method} {capture.url}?{query}`")
        lines.append("")
        lines.append(f"Status: {capture.status_code} {capture.reason}")
        lines.append("")
        lines.append(f"Elapsed: {capture.elapsed_ms:.2f} ms")
        lines.append("")
        content_type = capture.headers.get("content-type", "")
        lines.append(f"Content-Type: {content_type}")
        lines.append("")
        request_line = f"{capture.method} {capture.url}?{query}" if query else f"{capture.method} {capture.url}"
        if _is_html_response(content_type, capture.text):
            lines.extend(_html_source_and_preview_blocks(capture.text or "", request_line))
        elif capture.text is not None:
            lines.append("```")
            lines.append(capture.text.rstrip())
            lines.append("```")
            lines.append("")
        elif capture.arrow_table is not None:
            lines.append(_arrow_table_markdown(capture.arrow_table))
            lines.append("")
        else:
            lines.append(f"(binary body, {len(capture.body)} bytes)")
            lines.append("")
    lines.append("## Build artifacts")
    lines.append("")
    lines.append(format_listing(build_listing))
    lines.append("")
    lines.append("## Storage artifacts")
    lines.append("")
    lines.append(format_listing(storage_listing))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_End of demo._")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    demo_dir = SCRIPT_DIR
    repo_root = REPO_ROOT
    build_dir = repo_root / "routes_build"
    storage_dir = repo_root / "storage"

    compile_capture: CommandCapture | None = None
    server_run: ServerRun | None = None
    http_captures: list[HttpCapture] = []

    snapshots: list[DirectorySnapshot] = []
    build_listing = DirectoryListing(root=build_dir, files=[])
    storage_listing = DirectoryListing(root=storage_dir, files=[])

    snapshots.append(DirectorySnapshot.create(build_dir))
    snapshots.append(DirectorySnapshot.create(storage_dir))

    timestamp = datetime.now(timezone.utc)

    try:
        for snapshot in snapshots:
            snapshot.wipe(recreate=True)

        compile_command = [
            sys.executable,
            "-m",
            "webbed_duck.cli",
            "compile",
            "--source",
            str(repo_root / "routes_src"),
            "--build",
            str(build_dir),
        ]
        compile_capture = run_command(compile_command, cwd=repo_root)

        host = "127.0.0.1"
        port = 8765
        serve_command = [
            sys.executable,
            "-m",
            "webbed_duck.cli",
            "serve",
            "--no-watch",
            "--no-auto-compile",
            "--build",
            str(build_dir),
            "--config",
            str(repo_root / "config.toml"),
            "--host",
            host,
            "--port",
            str(port),
        ]
        env = os.environ.copy()
        env.setdefault("WEBDUCK_SKIP_CHARTJS_DOWNLOAD", "1")
        start = time.perf_counter()
        process, stdout_lines, stderr_lines, stdout_thread, stderr_thread = launch_server(
            serve_command,
            cwd=repo_root,
            env=env,
            host=host,
            port=port,
        )
        try:
            http_captures.append(
                request_route(host, port, label="HTML (table)", params={"name": "Ada", "format": "html_t"})
            )
            http_captures.append(
                request_route(host, port, label="CSV download", params={"name": "Ada", "format": "csv"})
            )
            http_captures.append(
                request_route(host, port, label="Arrow stream", params={"name": "Ada", "format": "arrow"})
            )
        finally:
            stop_server(process)
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
        duration = time.perf_counter() - start
        server_run = ServerRun(
            command=serve_command,
            returncode=process.returncode if process.returncode is not None else -1,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
            duration_s=duration,
            host=host,
            port=port,
        )

        build_listing = collect_listing(build_dir)
        storage_listing = collect_listing(storage_dir)
    finally:
        for snapshot in snapshots:
            snapshot.restore()
        for snapshot in snapshots:
            snapshot.cleanup()

    if compile_capture is None or server_run is None:
        raise RuntimeError("Demo generation did not complete successfully")

    markdown = generate_markdown(
        timestamp=timestamp,
        compile_capture=compile_capture,
        server_run=server_run,
        http_captures=http_captures,
        build_listing=build_listing,
        storage_listing=storage_listing,
    )
    output_path = demo_dir / "demo.md"
    output_path.write_text(markdown, encoding="utf-8")


if __name__ == "__main__":
    main()
