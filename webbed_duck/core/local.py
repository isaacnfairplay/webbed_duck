from __future__ import annotations

from pathlib import Path
from typing import Mapping, MutableMapping, Sequence

from ..config import Config, load_config
from ..server.overlay import OverlayStore, apply_overrides
from ..server.postprocess import table_to_records
from ..server.preprocess import run_preprocessors
from ..server.app import _execute_sql  # type: ignore[attr-defined]
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

    values, ordered = _prepare_parameters(route, params)
    processed = run_preprocessors(route.preprocess, values, route=route, request=None)
    bound = _order_from_processed(route, processed)
    table = _execute_sql(route.prepared_sql, bound)
    overlays = OverlayStore(config.server.storage_root)
    table = apply_overrides(table, route.metadata, overlays.list_for_route(route.id))

    fmt = format.lower()
    if fmt in {"arrow", "table"}:
        return table
    if fmt == "records":
        return table_to_records(table)
    raise ValueError(f"Unsupported format '{format}'")


def _prepare_parameters(route: RouteDefinition, provided: Mapping[str, object]) -> tuple[dict[str, object | None], list[object | None]]:
    values: MutableMapping[str, object | None] = {}
    for spec in route.params:
        if spec.name in provided:
            raw = provided[spec.name]
            if raw is None:
                values[spec.name] = None
            elif isinstance(raw, str):
                values[spec.name] = spec.convert(raw)
            else:
                values[spec.name] = raw
        else:
            if spec.default is not None:
                values[spec.name] = spec.default
            elif spec.required:
                raise ValueError(f"Missing required parameter '{spec.name}'")
            else:
                values[spec.name] = None
    ordered = []
    for name in route.param_order:
        if name not in values:
            raise ValueError(f"Parameter '{name}' was referenced in SQL but not provided")
        ordered.append(values[name])
    return dict(values), ordered


def _order_from_processed(route: RouteDefinition, processed: Mapping[str, object | None]) -> list[object | None]:
    ordered: list[object | None] = []
    for name in route.param_order:
        if name in processed:
            ordered.append(processed[name])
            continue
        spec = route.find_param(name)
        if spec is None:
            ordered.append(None)
            continue
        if spec.default is not None:
            ordered.append(spec.default)
        elif spec.required:
            raise ValueError(f"Missing required parameter '{name}' after preprocessing")
        else:
            ordered.append(None)
    return ordered


def _find_route(routes: Sequence[RouteDefinition], route_id: str) -> RouteDefinition:
    for route in routes:
        if route.id == route_id:
            return route
    raise RouteNotFoundError(route_id)


__all__ = ["run_route", "RouteNotFoundError"]
