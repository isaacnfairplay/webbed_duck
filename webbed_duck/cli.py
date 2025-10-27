"""Command line interface for webbed_duck."""
from __future__ import annotations

import argparse
import datetime
import statistics
import sys
import threading
import time
from pathlib import Path
from typing import Mapping, Sequence

from .config import load_config
from .core.compiler import compile_routes
from .core.incremental import run_incremental
from .core.local import run_route


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="webbed-duck", description="webbed_duck developer tools")
    subparsers = parser.add_subparsers(dest="command")

    compile_parser = subparsers.add_parser("compile", help="Compile Markdown routes into Python modules")
    compile_parser.add_argument("--source", default="routes_src", help="Directory containing *.sql.md route files")
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

    watch_interval = config.server.watch_interval
    if args.watch_interval is not None:
        watch_interval = max(0.2, float(args.watch_interval))

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
    timings.sort()
    average = statistics.fmean(timings)
    p95_index = int(round(0.95 * (len(timings) - 1)))
    p95 = timings[p95_index]
    print(f"Route: {args.route_id}")
    print(f"Iterations: {iterations}")
    print(f"Rows (last run): {rows_returned}")
    print(f"Average latency: {average:.3f} ms")
    print(f"95th percentile latency: {p95:.3f} ms")
    return 0


def _start_watcher(app, source_dir: Path, build_dir: Path, interval: float) -> tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_watch_source,
        args=(app, source_dir, build_dir, max(0.2, float(interval)), stop_event),
        daemon=True,
        name="webbed-duck-watch",
    )
    thread.start()
    print(f"[webbed-duck] Watching {source_dir} for changes (interval={interval:.2f}s)")
    return stop_event, thread


def _watch_source(app, source_dir: Path, build_dir: Path, interval: float, stop_event: threading.Event) -> None:
    from .core.routes import load_compiled_routes

    snapshot = _snapshot_source(source_dir)
    while not stop_event.wait(interval):
        current = _snapshot_source(source_dir)
        if current == snapshot:
            continue
        snapshot = current
        try:
            compile_routes(source_dir, build_dir)
            routes = load_compiled_routes(build_dir)
        except Exception as exc:  # pragma: no cover - runtime safeguard
            print(f"[webbed-duck] Watcher failed to compile routes: {exc}", file=sys.stderr)
            continue
        try:
            reload_fn = getattr(app.state, "reload_routes", None)
            if reload_fn is None:
                raise RuntimeError("Application does not expose a reload_routes handler")
            reload_fn(routes)
        except Exception as exc:  # pragma: no cover - runtime safeguard
            print(f"[webbed-duck] Watcher failed to reload routes: {exc}", file=sys.stderr)
            continue
        print(f"[webbed-duck] Reloaded {len(routes)} route(s) from {source_dir}")


def _snapshot_source(source_dir: Path) -> dict[str, tuple[float, int]]:
    snapshot: dict[str, tuple[float, int]] = {}
    if not source_dir.exists():
        return snapshot
    patterns = ("*.toml", "*.sql", "*.sql.md")
    for pattern in patterns:
        for path in sorted(source_dir.rglob(pattern)):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:  # pragma: no cover - filesystem race
                continue
            snapshot[str(path.relative_to(source_dir))] = (stat.st_mtime, stat.st_size)
    return snapshot


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
