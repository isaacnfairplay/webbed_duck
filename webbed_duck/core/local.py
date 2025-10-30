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


class LocalRouteRunner:
    """Lightweight helper for executing compiled routes without HTTP."""

    def __init__(
        self,
        *,
        routes: Sequence[RouteDefinition] | None = None,
        build_dir: str | Path = "routes_build",
        config: Config | None = None,
    ) -> None:
        if routes is None:
            routes = load_compiled_routes(build_dir)
        self._routes = {route.id: route for route in routes}
        if config is None:
            config = load_config(None)
        self._config = config
        self._cache_store = CacheStore(self._config.server.storage_root)
        self._overlay_store = OverlayStore(self._config.server.storage_root)

    def run(
        self,
        route_id: str,
        params: Mapping[str, object] | None = None,
        *,
        format: str | None = None,
    ) -> object:
        """Execute ``route_id`` and return the requested format."""

        params = params or {}
        route = self._routes.get(route_id)
        if route is None:
            raise RouteNotFoundError(route_id)
        resolved_format = _resolve_format(route, format)
        executor = RouteExecutor(
            self._routes,
            cache_store=self._cache_store,
            config=self._config,
        )

        try:
            cache_result = executor.execute_relation(
                route,
                params,
                offset=0,
                limit=None,
            )
        except RouteExecutionError as exc:
            raise ValueError(str(exc)) from exc

        table = apply_overrides(
            cache_result.table,
            route.metadata,
            self._overlay_store.list_for_route(route.id),
        )

        if resolved_format in {"arrow", "table"}:
            return table
        if resolved_format in {"json", "records"}:
            return table_to_records(table)
        raise ValueError(f"Unsupported format '{resolved_format}'")


def run_route(
    route_id: str,
    params: Mapping[str, object] | None = None,
    *,
    routes: Sequence[RouteDefinition] | None = None,
    build_dir: str | Path = "routes_build",
    config: Config | None = None,
    format: str | None = None,
) -> object:
    """Execute ``route_id`` directly without HTTP transport."""

    runner = LocalRouteRunner(routes=routes, build_dir=build_dir, config=config)
    return runner.run(route_id, params=params, format=format)


def _resolve_format(route: RouteDefinition, requested: str | None) -> str:
    raw = requested if requested is not None else route.default_format
    fmt = (raw or "arrow").lower()
    allowed = {item.lower() for item in route.allowed_formats} if route.allowed_formats else None
    if allowed and fmt not in allowed:
        raise ValueError(f"Format '{fmt}' not enabled for route '{route.id}'")
    supported = {"arrow", "table", "json", "records"}
    if fmt not in supported:
        raise ValueError(f"Unsupported format '{fmt}'")
    return fmt


__all__ = ["LocalRouteRunner", "run_route", "RouteNotFoundError"]
