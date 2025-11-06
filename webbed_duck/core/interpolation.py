from __future__ import annotations

import decimal
import json
import re
from typing import Any, Mapping, Sequence

try:  # pragma: no cover - optional dependency for type checking
    from fastapi import Request
except ModuleNotFoundError:  # pragma: no cover - fallback when FastAPI not installed
    Request = Any  # type: ignore[misc,assignment]

from ..config import InterpolationConfig
from .routes import ParameterSpec, RouteDefinition, TemplateSlot


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_FILE_FUNCTION_PATTERN = re.compile(
    r"\b("  # start a group of known file/path helpers
    r"read_parquet|read_csv|read_csv_auto|read_json|read_json_auto|read_ipc|read_arrow|"
    r"read_orc|read_avro|csv_scan|parquet_scan|json_scan|read_ndjson|read_excel|glob"
    r")\s*\((?P<body>[^)]*)",
    re.IGNORECASE | re.DOTALL,
)


class TemplateInterpolationError(RuntimeError):
    """Raised when a template-only parameter cannot be interpolated."""


def render_sql(
    route: RouteDefinition,
    params: Mapping[str, object],
    *,
    config: InterpolationConfig,
    request: Request | None = None,
) -> str:
    """Render ``route.prepared_sql`` using template-only parameters."""

    if not route.template_slots:
        _enforce_db_param_policy(route.prepared_sql, config, route_id=route.id)
        return route.prepared_sql

    spec_map: dict[str, ParameterSpec] = {spec.name: spec for spec in route.params}
    rendered = route.prepared_sql
    for slot in route.template_slots:
        spec = spec_map.get(slot.param)
        if spec is None:
            raise TemplateInterpolationError(
                f"Route '{route.id}' references unknown template parameter '{slot.param}'"
            )
        value = params.get(slot.param, spec.default if spec.default is not None else None)
        rendered_value = _render_template_value(
            route,
            slot,
            spec,
            value,
            request=request,
        )
        rendered = rendered.replace(slot.marker, rendered_value)

    _enforce_db_param_policy(rendered, config, route_id=route.id)
    return rendered


def _render_template_value(
    route: RouteDefinition,
    slot: TemplateSlot,
    spec: ParameterSpec,
    value: object,
    *,
    request: Request | None,
) -> str:
    guard_checked = _evaluate_guard(route, spec, value, request=request)
    template_meta = spec.template if isinstance(spec.template, Mapping) else {}
    policy = str(template_meta.get("policy", "literal")).lower()
    working = guard_checked
    policy_override: str | None = None

    for filter_name in slot.filters:
        normalized = filter_name.lower()
        if normalized in {"lower", "lowercase"}:
            working = _ensure_text(working, route, spec).lower()
        elif normalized in {"upper", "uppercase"}:
            working = _ensure_text(working, route, spec).upper()
        elif normalized in {"identifier", "as_identifier"}:
            policy_override = "identifier"
        elif normalized in {"literal", "as_literal"}:
            policy_override = "literal"
        elif normalized == "json":
            working = json.dumps(working)
            policy_override = "literal"
        else:
            raise TemplateInterpolationError(
                f"Unsupported filter '{filter_name}' for parameter '{spec.name}' on route '{route.id}'"
            )

    final_policy = policy_override or policy
    return _apply_policy(route, spec, working, final_policy)


def _ensure_text(value: object, route: RouteDefinition, spec: ParameterSpec) -> str:
    if value is None:
        raise TemplateInterpolationError(
            f"Template parameter '{spec.name}' on route '{route.id}' cannot be null when applying string filters"
        )
    return str(value)


def _apply_policy(
    route: RouteDefinition,
    spec: ParameterSpec,
    value: object,
    policy: str,
) -> str:
    normalized = policy.lower()
    if normalized == "identifier":
        text = _ensure_text(value, route, spec)
        if not _IDENTIFIER_PATTERN.match(text):
            raise TemplateInterpolationError(
                f"Template parameter '{spec.name}' must produce a valid identifier for route '{route.id}'"
            )
        return text
    if normalized == "raw":
        if value is None:
            raise TemplateInterpolationError(
                f"Template parameter '{spec.name}' cannot be NULL for policy 'raw' on route '{route.id}'"
            )
        return str(value)
    if normalized == "literal":
        return _sql_literal(value)
    raise TemplateInterpolationError(
        f"Template parameter '{spec.name}' on route '{route.id}' uses unsupported policy '{policy}'"
    )


def _sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float, decimal.Decimal)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "(" + ", ".join(_sql_literal(item) for item in value) + ")"
    text = str(value)
    escaped = text.replace("'", "''")
    return f"'{escaped}'"


def _evaluate_guard(
    route: RouteDefinition,
    spec: ParameterSpec,
    value: object,
    *,
    request: Request | None,
) -> object:
    guard = spec.guard if isinstance(spec.guard, Mapping) else None
    if not guard:
        return value
    mode = str(guard.get("mode", "")).lower()
    if mode == "path":
        if value is None:
            raise TemplateInterpolationError(
                f"Template parameter '{spec.name}' on route '{route.id}' requires a value"
            )
        text = str(value)
        if ".." in text.split("/"):
            raise TemplateInterpolationError(
                f"Template parameter '{spec.name}' on route '{route.id}' cannot contain '..' segments"
            )
        if re.match(r"^[A-Za-z]:", text) or text.startswith("/"):
            raise TemplateInterpolationError(
                f"Template parameter '{spec.name}' on route '{route.id}' must be a relative path"
            )
        if "\\" in text:
            raise TemplateInterpolationError(
                f"Template parameter '{spec.name}' on route '{route.id}' must not contain backslashes"
            )
        return text
    if mode == "choices":
        allowed = guard.get("values")
        if not isinstance(allowed, Sequence):
            raise TemplateInterpolationError(
                f"Guard for parameter '{spec.name}' on route '{route.id}' must define a 'values' list"
            )
        if value not in allowed:
            raise TemplateInterpolationError(
                f"Template parameter '{spec.name}' on route '{route.id}' must be one of {list(allowed)}"
            )
        return value
    if mode == "role":
        required = guard.get("role")
        if required is None:
            raise TemplateInterpolationError(
                f"Guard for parameter '{spec.name}' on route '{route.id}' must define 'role'"
            )
        if request is None:
            raise TemplateInterpolationError(
                f"Template parameter '{spec.name}' on route '{route.id}' requires request context for role guard"
            )
        roles = _extract_roles(request)
        if required not in roles:
            raise TemplateInterpolationError(
                f"Role '{required}' is required to use parameter '{spec.name}' on route '{route.id}'"
            )
        return value
    raise TemplateInterpolationError(
        f"Template guard mode '{mode}' is not supported for parameter '{spec.name}' on route '{route.id}'"
    )


def _extract_roles(request: Request) -> Sequence[str]:
    roles = []
    state = getattr(request, "state", None)
    if state is not None:
        for attr in ("roles", "user_roles", "principal_roles"):
            candidate = getattr(state, attr, None)
            if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
                roles = list(candidate)
                break
    scope_roles = request.scope.get("roles") if hasattr(request, "scope") else None  # type: ignore[attr-defined]
    if scope_roles and not roles:
        if isinstance(scope_roles, Sequence) and not isinstance(scope_roles, (str, bytes)):
            roles = list(scope_roles)
    return roles


def _enforce_db_param_policy(
    sql: str,
    config: InterpolationConfig,
    *,
    route_id: str,
) -> None:
    if not config.forbid_db_params_in_file_functions:
        return
    for match in _FILE_FUNCTION_PATTERN.finditer(sql):
        body = match.group("body")
        if body and "$" in body:
            func = match.group(1)
            raise TemplateInterpolationError(
                f"Route '{route_id}' forbids DuckDB parameters inside {func}() due to interpolation settings"
            )


__all__ = ["TemplateInterpolationError", "render_sql"]
