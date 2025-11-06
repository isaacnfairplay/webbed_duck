"""Render SQL templates with template-only parameters."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
from pathlib import PurePosixPath
from typing import Mapping, Sequence

from ..config import InterpolationConfig
from ..core.routes import ParameterSpec, RouteDefinition, TemplateCall

_BINDING_PATTERN = re.compile(r"\$(?P<name>[A-Za-z_][A-Za-z0-9_]*)")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_FILE_FUNCTION_PATTERN = re.compile(
    r"\b(read_(?:csv|csv_auto|json|parquet|avro)|parquet_scan)\s*\((?P<args>[^)]*)",
    re.IGNORECASE,
)


class InterpolationError(RuntimeError):
    """Raised when template interpolation cannot be performed safely."""


@dataclass(slots=True)
class _TemplateContext:
    route: RouteDefinition
    params: Mapping[str, object]

    def value_for(self, spec: ParameterSpec) -> object:
        if spec.name in self.params:
            value = self.params[spec.name]
        elif spec.default is not None:
            value = spec.default
        else:
            value = None
        if value is None:
            raise InterpolationError(
                f"Template parameter '{spec.name}' requires a value for route '{self.route.id}'"
            )
        return value


def render_interpolated_sql(
    route: RouteDefinition,
    params: Mapping[str, object],
    *,
    config: InterpolationConfig,
) -> tuple[str, set[str]]:
    """Render ``route.prepared_sql`` by substituting template placeholders."""

    sql = route.prepared_sql
    if route.template_calls:
        spec_map = {spec.name: spec for spec in route.params}
        ctx = _TemplateContext(route=route, params=params)
        for call in route.template_calls:
            spec = spec_map.get(call.param)
            if spec is None:
                raise InterpolationError(
                    f"Template call references unknown parameter '{call.param}' on route '{route.id}'"
                )
            raw_value = ctx.value_for(spec)
            rendered = _render_template_value(spec, raw_value, call.filters, route)
            sql = sql.replace(call.token, rendered)
    _enforce_file_function_policy(sql, config, route_id=route.id)
    binding_names = {
        match.group("name")
        for match in _BINDING_PATTERN.finditer(sql)
        if match.group("name")
    }
    return sql, binding_names


def _render_template_value(
    spec: ParameterSpec,
    value: object,
    filters: Sequence[str],
    route: RouteDefinition,
) -> str:
    _evaluate_guard(spec, value, route)
    working = value
    rendered: str | None = None
    for filter_name in filters:
        normalized = filter_name.lower()
        if normalized in _VALUE_FILTERS:
            working = _VALUE_FILTERS[normalized](working, spec=spec, route=route)
            continue
        renderer = _RENDER_FILTERS.get(normalized)
        if renderer is None:
            raise InterpolationError(
                f"Unsupported template filter '{filter_name}' for parameter '{spec.name}'"
            )
        rendered = renderer(working, spec=spec, route=route)
        working = rendered
    if rendered is None:
        policy = _resolve_policy(spec)
        renderer = _RENDER_FILTERS.get(policy)
        if renderer is None:
            raise InterpolationError(
                f"Unsupported template policy '{policy}' for parameter '{spec.name}'"
            )
        rendered = renderer(working, spec=spec, route=route)
    if not isinstance(rendered, str):
        rendered = str(rendered)
    return rendered


def _resolve_policy(spec: ParameterSpec) -> str:
    template_block = spec.template or {}
    policy_raw = template_block.get("policy") if isinstance(template_block, Mapping) else None
    if policy_raw is None:
        return "literal"
    return str(policy_raw).lower()


def _evaluate_guard(spec: ParameterSpec, value: object, route: RouteDefinition) -> None:
    guard = spec.guard or {}
    mode_raw = guard.get("mode") if isinstance(guard, Mapping) else None
    if mode_raw is None:
        return
    mode = str(mode_raw).lower()
    if mode == "path":
        _validate_path(value, spec=spec, route=route)


def _render_literal(value: object, *, spec: ParameterSpec, route: RouteDefinition) -> str:
    text = str(value)
    escaped = text.replace("'", "''")
    return f"'{escaped}'"


def _render_identifier(value: object, *, spec: ParameterSpec, route: RouteDefinition) -> str:
    text = str(value)
    if not _IDENTIFIER_PATTERN.match(text):
        raise InterpolationError(
            f"Value '{text}' for parameter '{spec.name}' must be a valid identifier"
        )
    return text


def _render_path(value: object, *, spec: ParameterSpec, route: RouteDefinition) -> str:
    normalized = _validate_path(value, spec=spec, route=route)
    escaped = normalized.replace("'", "''")
    return f"'{escaped}'"


def _value_lower(value: object, *, spec: ParameterSpec, route: RouteDefinition) -> object:
    text = str(value)
    return text.lower()


def _value_upper(value: object, *, spec: ParameterSpec, route: RouteDefinition) -> object:
    text = str(value)
    return text.upper()


def _value_basename(value: object, *, spec: ParameterSpec, route: RouteDefinition) -> object:
    text = str(value)
    normalized = text.replace("\\", "/")
    return os.path.basename(normalized)


_RENDER_FILTERS = {
    "literal": _render_literal,
    "identifier": _render_identifier,
    "path": _render_path,
}

_VALUE_FILTERS = {
    "lower": _value_lower,
    "upper": _value_upper,
    "basename": _value_basename,
}


def _validate_path(value: object, *, spec: ParameterSpec, route: RouteDefinition) -> str:
    text = str(value)
    normalized = text.replace("\\", "/")
    if not normalized:
        raise InterpolationError(
            f"Parameter '{spec.name}' must not be empty when used for path interpolation"
        )
    if normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized:
        raise InterpolationError(
            f"Parameter '{spec.name}' cannot reference absolute or parent-relative paths"
        )
    if re.match(r"^[A-Za-z]:", normalized):
        raise InterpolationError(
            f"Parameter '{spec.name}' cannot reference absolute Windows drive paths"
        )
    if "://" in normalized:
        raise InterpolationError(
            f"Parameter '{spec.name}' cannot include URL-style schemes"
        )
    # Normalize redundant segments without resolving to filesystem paths
    collapsed = str(PurePosixPath(normalized))
    return collapsed


def _enforce_file_function_policy(sql: str, config: InterpolationConfig, *, route_id: str) -> None:
    if not config.forbid_db_params_in_file_functions:
        return
    for match in _FILE_FUNCTION_PATTERN.finditer(sql):
        args = match.group("args") or ""
        if "$" in args:
            func = match.group(1)
            raise InterpolationError(
                f"Route '{route_id}' cannot bind parameters inside {func}() while"
                " interpolation.forbid_db_params_in_file_functions is enabled"
            )


__all__ = [
    "InterpolationError",
    "render_interpolated_sql",
]
