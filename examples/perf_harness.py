"""Lightweight performance harness for executing compiled routes."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Mapping, Sequence

from webbed_duck.config import Config, load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.local import run_route
from webbed_duck.core.routes import RouteDefinition, load_compiled_routes


def benchmark_route(
    route_id: str,
    *,
    iterations: int,
    routes: Sequence[RouteDefinition],
    config: Config,
    params: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    """Execute ``route_id`` ``iterations`` times and capture timing stats."""

    params = params or {}
    start = time.perf_counter()
    row_count = 0
    for _ in range(iterations):
        table = run_route(route_id, params=params, routes=routes, config=config)
        row_count = table.num_rows
    total_ms = (time.perf_counter() - start) * 1000
    return {
        "route_id": route_id,
        "iterations": iterations,
        "total_ms": round(total_ms, 3),
        "avg_ms": round(total_ms / max(1, iterations), 3),
        "row_count": row_count,
    }


def _parse_params(values: Sequence[str]) -> Mapping[str, object]:
    parsed: dict[str, object] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"Parameter must use key=value format: {item!r}")
        key, value = item.split("=", 1)
        parsed[key] = value
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("route", help="Route identifier to benchmark")
    parser.add_argument("--routes-src", type=Path, default=Path("routes_src"), help="Route source directory")
    parser.add_argument("--routes-build", type=Path, default=Path("routes_build"), help="Compiled route directory")
    parser.add_argument("--config", type=Path, default=None, help="Optional config.toml path")
    parser.add_argument("--iterations", type=int, default=5, help="Number of iterations to run")
    parser.add_argument("--param", action="append", default=[], help="Parameter overrides in key=value format")
    args = parser.parse_args(argv)

    if args.routes_src.exists():
        compile_routes(args.routes_src, args.routes_build)

    routes = load_compiled_routes(args.routes_build)
    config = load_config(args.config) if args.config else load_config(None)
    params = _parse_params(args.param)
    stats = benchmark_route(args.route, iterations=args.iterations, routes=routes, config=config, params=params)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI wrapper
    raise SystemExit(main())
