"""Command line interface for webbed_duck."""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path
from typing import Sequence

from .config import load_config
from .core.compiler import compile_routes
from .core.incremental import run_incremental


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="webbed-duck", description="webbed_duck developer tools")
    subparsers = parser.add_subparsers(dest="command")

    compile_parser = subparsers.add_parser("compile", help="Compile Markdown routes into Python modules")
    compile_parser.add_argument("--source", default="routes_src", help="Directory containing *.sql.md route files")
    compile_parser.add_argument("--build", default="routes_build", help="Destination directory for compiled routes")

    serve_parser = subparsers.add_parser("serve", help="Run the development server")
    serve_parser.add_argument("--build", default="routes_build", help="Directory containing compiled routes")
    serve_parser.add_argument("--source", default=None, help="Optional source directory to compile before serving")
    serve_parser.add_argument("--config", default="config.toml", help="Path to configuration file")
    serve_parser.add_argument("--host", default=None, help="Override server host")
    serve_parser.add_argument("--port", type=int, default=None, help="Override server port")
    serve_parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload (development only)")

    incr_parser = subparsers.add_parser("run-incremental", help="Run an incremental route over a date range")
    incr_parser.add_argument("route_id", help="ID of the compiled route to execute")
    incr_parser.add_argument("--param", required=True, help="Cursor parameter name")
    incr_parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    incr_parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    incr_parser.add_argument("--build", default="routes_build", help="Directory containing compiled routes")
    incr_parser.add_argument("--config", default="config.toml", help="Configuration file")

    args = parser.parse_args(argv)
    if args.command == "compile":
        return _cmd_compile(args.source, args.build)
    if args.command == "serve":
        return _cmd_serve(args)
    if args.command == "run-incremental":
        return _cmd_run_incremental(args)

    parser.print_help()
    return 1


def _cmd_compile(source: str, build: str) -> int:
    compiled = compile_routes(source, build)
    print(f"Compiled {len(compiled)} route(s) to {build}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from .core.routes import load_compiled_routes
    from .server.app import create_app

    build_dir = Path(args.build)
    if args.source:
        compile_routes(args.source, build_dir)

    routes = load_compiled_routes(build_dir)
    config = load_config(args.config)
    app = create_app(routes, config)

    host = args.host or config.server.host
    port = args.port or config.server.port

    import uvicorn

    uvicorn.run(app, host=host, port=port, reload=args.reload)
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


def _parse_date(value: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argument validation
        raise SystemExit(f"Invalid date: {value}") from exc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
