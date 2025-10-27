from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from ..config import Config, load_config
from ..server.cache import CacheStore
from ..server.execution import RouteExecutionError, RouteExecutor
from ..server.overlay import OverlayStore, apply_overrides
from ..server.postprocess import table_to_records
from .routes import RouteDefinition, load_compiled_routes


class RouteNotFoundError(KeyError):
    """Raised when a route identifier is unknown."""


def run_route(
    route_id: str,
    params: Mapping[str, object] | None = None,
    *,
    routes: Sequence[RouteDefinition] | None = None,
    build_dir: str | Path = "routes_build",
    config: Config | None = None,
    format: str = "arrow",
) -> object:
    """Execute ``route_id`` directly without HTTP transport."""

    params = params or {}
    if routes is None:
        routes = load_compiled_routes(build_dir)
    route = _find_route(routes, route_id)
    if config is None:
        config = load_config(None)

    cache_store = CacheStore(config.server.storage_root)
    executor = RouteExecutor({item.id: item for item in routes}, cache_store=cache_store, config=config)
    try:
        cache_result = executor.execute_relation(route, params, offset=0, limit=None)
    except RouteExecutionError as exc:
        raise ValueError(str(exc)) from exc
    table = cache_result.table
    overlays = OverlayStore(config.server.storage_root)
    table = apply_overrides(table, route.metadata, overlays.list_for_route(route.id))

    fmt = format.lower()
    if fmt in {"arrow", "table"}:
        return table
    if fmt == "records":
        return table_to_records(table)
    raise ValueError(f"Unsupported format '{format}'")


def _find_route(routes: Sequence[RouteDefinition], route_id: str) -> RouteDefinition:
    for route in routes:
        if route.id == route_id:
            return route
    raise RouteNotFoundError(route_id)


__all__ = ["run_route", "RouteNotFoundError"]
