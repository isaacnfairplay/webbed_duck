"""Command line interface for webbed_duck."""
from __future__ import annotations

import argparse
import datetime
import statistics
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .config import load_config
from .core.compiler import compile_routes
from .core.incremental import run_incremental
from .core.local import run_route

WATCH_INTERVAL_MIN = 0.2


@dataclass(frozen=True)
class SourceFingerprint:
    """Filesystem fingerprint for a route source directory."""

    files: Mapping[str, tuple[float, int]]

    def has_changed(self, other: "SourceFingerprint") -> bool:
        """Return ``True`` when ``other`` differs from this snapshot."""

        return dict(self.files) != dict(other.files)


@dataclass(frozen=True)
class PerfStats:
    """Summarised latency metrics for ``webbed-duck perf``."""

    iterations: int
    rows_returned: int
    average_ms: float
    p95_ms: float

    @classmethod
    def from_timings(cls, timings: Sequence[float], rows_returned: int) -> "PerfStats":
        if not timings:
            raise ValueError("timings must contain at least one value")
        ordered = sorted(timings)
        average = statistics.fmean(ordered)
        p95_index = int(round(0.95 * (len(ordered) - 1)))
        p95 = ordered[p95_index]
        return cls(iterations=len(ordered), rows_returned=rows_returned, average_ms=average, p95_ms=p95)

    def format_report(self, route_id: str) -> str:
        lines = [
            f"Route: {route_id}",
            f"Iterations: {self.iterations}",
            f"Rows (last run): {self.rows_returned}",
            f"Average latency: {self.average_ms:.3f} ms",
            f"95th percentile latency: {self.p95_ms:.3f} ms",
        ]
        return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="webbed-duck", description="webbed_duck developer tools")
    subparsers = parser.add_subparsers(dest="command")

    compile_parser = subparsers.add_parser("compile", help="Compile Markdown routes into Python modules")
    compile_parser.add_argument(
        "--source",
        default="routes_src",
        help="Directory containing TOML/SQL route sidecars",
    )
    compile_parser.add_argument("--build", default="routes_build", help="Destination directory for compiled routes")

    serve_parser = subparsers.add_parser("serve", help="Run the development server")
    serve_parser.add_argument("--build", default=None, help="Directory containing compiled routes")
    serve_parser.add_argument("--source", default=None, help="Optional source directory to compile before serving")
    serve_parser.add_argument("--config", default="config.toml", help="Path to configuration file")
    serve_parser.add_argument("--host", default=None, help="Override server host")
    serve_parser.add_argument("--port", type=int, default=None, help="Override server port")
    serve_parser.add_argument("--no-auto-compile", action="store_true", help="Skip automatic compilation on startup")
    serve_parser.add_argument("--watch", action="store_true", help="Watch the source directory and hot-reload routes")
    serve_parser.add_argument("--no-watch", action="store_true", help="Disable watch mode even if enabled in config")
    serve_parser.add_argument(
        "--watch-interval",
        type=float,
        default=None,
        help="Polling interval in seconds when watching for changes",
    )

    incr_parser = subparsers.add_parser("run-incremental", help="Run an incremental route over a date range")
    incr_parser.add_argument("route_id", help="ID of the compiled route to execute")
    incr_parser.add_argument("--param", required=True, help="Cursor parameter name")
    incr_parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    incr_parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    incr_parser.add_argument("--build", default="routes_build", help="Directory containing compiled routes")
    incr_parser.add_argument("--config", default="config.toml", help="Configuration file")

    perf_parser = subparsers.add_parser("perf", help="Run a compiled route repeatedly and report latency stats")
    perf_parser.add_argument("route_id", help="ID of the compiled route to execute")
    perf_parser.add_argument("--build", default="routes_build", help="Directory containing compiled routes")
    perf_parser.add_argument("--config", default="config.toml", help="Configuration file")
    perf_parser.add_argument("--iterations", type=int, default=5, help="Number of executions to measure")
    perf_parser.add_argument("--param", action="append", default=[], help="Parameter override in the form name=value")

    args = parser.parse_args(argv)
    if args.command == "compile":
        return _cmd_compile(args.source, args.build)
    if args.command == "serve":
        return _cmd_serve(args)
    if args.command == "run-incremental":
        return _cmd_run_incremental(args)
    if args.command == "perf":
        return _cmd_perf(args)

    parser.print_help()
    return 1


def _cmd_compile(source: str, build: str) -> int:
    compiled = compile_routes(source, build)
    print(f"Compiled {len(compiled)} route(s) to {build}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from .core.routes import load_compiled_routes
    from .server.app import create_app

    config = load_config(args.config)

    build_dir = Path(args.build) if args.build else Path(config.server.build_dir)
    source_dir = Path(args.source) if args.source else config.server.source_dir
    if source_dir is not None:
        source_dir = Path(source_dir)

    auto_compile = config.server.auto_compile
    if args.no_auto_compile:
        auto_compile = False
    elif args.source is not None:
        auto_compile = True

    watch_enabled = config.server.watch
    if args.no_watch:
        watch_enabled = False
    elif args.watch:
        watch_enabled = True

    watch_interval = max(WATCH_INTERVAL_MIN, float(config.server.watch_interval))
    if args.watch_interval is not None:
        watch_interval = max(WATCH_INTERVAL_MIN, float(args.watch_interval))

    if auto_compile and source_dir is not None:
        try:
            compiled = compile_routes(source_dir, build_dir)
        except FileNotFoundError as exc:
            print(f"[webbed-duck] Auto-compile skipped: {exc}", file=sys.stderr)
        except Exception as exc:  # pragma: no cover - runtime safeguard
            print(f"[webbed-duck] Auto-compile failed: {exc}", file=sys.stderr)
            return 1
        else:
            print(f"[webbed-duck] Compiled {len(compiled)} route(s) from {source_dir} -> {build_dir}")

    try:
        routes = load_compiled_routes(build_dir)
    except FileNotFoundError as exc:
        print(f"[webbed-duck] {exc}", file=sys.stderr)
        return 1

    app = create_app(routes, config)

    stop_event: threading.Event | None = None
    watch_thread: threading.Thread | None = None
    if watch_enabled and source_dir is not None:
        stop_event, watch_thread = _start_watcher(app, source_dir, build_dir, watch_interval)
    elif watch_enabled and source_dir is None:
        print("[webbed-duck] Watch mode enabled but no source directory configured", file=sys.stderr)

    host = args.host or config.server.host
    port = args.port or config.server.port

    import uvicorn

    try:
        uvicorn.run(app, host=host, port=port)
    finally:
        if stop_event is not None:
            stop_event.set()
        if watch_thread is not None:
            watch_thread.join(timeout=2)
    return 0


def _cmd_run_incremental(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    start = _parse_date(args.start)
    end = _parse_date(args.end)
    results = run_incremental(
        args.route_id,
        cursor_param=args.param,
        start=start,
        end=end,
        config=config,
        build_dir=args.build,
    )
    for item in results:
        print(f"{item.route_id} {item.cursor_param}={item.value} rows={item.rows_returned}")
    return 0


def _cmd_perf(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    params = _parse_param_assignments(args.param)
    iterations = max(1, int(args.iterations))
    timings: list[float] = []
    rows_returned = 0
    for _ in range(iterations):
        start = time.perf_counter()
        table = run_route(
            args.route_id,
            params=params,
            build_dir=args.build,
            config=config,
            format="table",
        )
        elapsed = (time.perf_counter() - start) * 1000
        timings.append(elapsed)
        rows_returned = getattr(table, "num_rows", rows_returned)
    stats = PerfStats.from_timings(timings, rows_returned)
    print(stats.format_report(args.route_id))
    return 0


def _start_watcher(app, source_dir: Path, build_dir: Path, interval: float) -> tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()
    effective_interval = max(WATCH_INTERVAL_MIN, float(interval))
    thread = threading.Thread(
        target=_watch_source,
        args=(app, source_dir, build_dir, effective_interval, stop_event),
        daemon=True,
        name="webbed-duck-watch",
    )
    thread.start()
    print(
        f"[webbed-duck] Watching {source_dir} for changes (interval={effective_interval:.2f}s)"
    )
    return stop_event, thread


def _watch_source(app, source_dir: Path, build_dir: Path, interval: float, stop_event: threading.Event) -> None:
    snapshot = build_source_fingerprint(source_dir)
    while not stop_event.wait(interval):
        try:
            snapshot, count = _watch_iteration(app, source_dir, build_dir, snapshot)
        except Exception as exc:  # pragma: no cover - runtime safeguard
            print(f"[webbed-duck] Watcher failed to compile routes: {exc}", file=sys.stderr)
            continue
        if count:
            print(f"[webbed-duck] Reloaded {count} route(s) from {source_dir}")


def _compile_and_reload(
    app,
    source_dir: Path,
    build_dir: Path,
    *,
    compile_fn=compile_routes,
    load_fn=None,
) -> int:
    from .core.routes import load_compiled_routes

    loader = load_fn or load_compiled_routes
    compile_fn(source_dir, build_dir)
    routes = loader(build_dir)
    reload_fn = getattr(app.state, "reload_routes", None)
    if reload_fn is None:
        raise RuntimeError("Application does not expose a reload_routes handler")
    reload_fn(routes)
    return len(routes)


def _watch_iteration(
    app,
    source_dir: Path,
    build_dir: Path,
    snapshot: SourceFingerprint,
    *,
    compile_and_reload=_compile_and_reload,
) -> tuple[SourceFingerprint, int]:
    """Perform a single watch iteration and return the updated snapshot and reload count."""

    current = build_source_fingerprint(source_dir)
    if not snapshot.has_changed(current):
        return snapshot, 0
    count = compile_and_reload(app, source_dir, build_dir)
    return current, count


def build_source_fingerprint(
    source_dir: Path, *, patterns: Sequence[str] = ("*.toml", "*.sql", "*.md")
) -> SourceFingerprint:
    files: dict[str, tuple[float, int]] = {}
    root = Path(source_dir)
    if not root.exists():
        return SourceFingerprint(files)
    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:  # pragma: no cover - filesystem race
                continue
            files[str(path.relative_to(root))] = (stat.st_mtime, stat.st_size)
    return SourceFingerprint(files)


def _parse_param_assignments(pairs: Sequence[str]) -> Mapping[str, str]:
    params: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"Invalid parameter assignment: {pair}")
        name, value = pair.split("=", 1)
        params[name] = value
    return params


def _parse_date(value: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argument validation
        raise SystemExit(f"Invalid date: {value}") from exc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
