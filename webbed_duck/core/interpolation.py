from __future__ import annotations

"""SQL interpolation helpers for template-only parameters."""

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .routes import ParameterSpec
from ..config import InterpolationConfig


class InterpolationError(RuntimeError):
    """Raised when template interpolation fails at runtime."""


_TEMPLATE_PATTERN = re.compile(r"\{\{\s*(?P<expr>.*?)\s*\}\}", re.DOTALL)
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FILE_FUNCTIONS = {
    "read_csv",
    "read_csv_auto",
    "read_parquet",
    "read_json",
    "read_json_auto",
    "read_ndjson",
    "read_orc",
    "read_xml",
    "read_text",
    "read_excel",
    "read_avro",
    "read_ipc",
    "read_arrow",
    "parquet_scan",
    "parquet_metadata",
    "json_scan",
    "csv_scan",
    "text_scan",
}

_FILE_FUNCTION_PATTERN = re.compile(
    r"\b(" + "|".join(sorted(_FILE_FUNCTIONS)) + r")\s*\((?P<args>[^)]*)\)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(slots=True)
class InterpolationSlot:
    name: str
    filters: tuple[str, ...]
    expr: str
    line: int
    column: int
    requires_path_guard: bool = False


@dataclass(slots=True)
class InterpolationProgram:
    segments: tuple[str, ...]
    slots: tuple[InterpolationSlot, ...]
    template_sql: str

    @property
    def has_slots(self) -> bool:
        return bool(self.slots)


def build_interpolation_program(
    sql: str,
    params: Sequence[ParameterSpec],
    *,
    source_path: Path,
) -> InterpolationProgram:
    param_map = {spec.name: spec for spec in params}
    segments: list[str] = []
    slots: list[InterpolationSlot] = []
    cursor = 0

    for match in _TEMPLATE_PATTERN.finditer(sql):
        start, end = match.span()
        expr = match.group("expr")
        if expr is None:
            continue
        segments.append(sql[cursor:start])
        slot = _parse_slot(expr, param_map, match.start(), sql, source_path)
        slots.append(slot)
        cursor = end
    segments.append(sql[cursor:])

    template_sql_parts: list[str] = []
    for index, segment in enumerate(segments):
        template_sql_parts.append(segment)
        if index < len(slots):
            template_sql_parts.append(_slot_marker(index))
    template_sql = "".join(template_sql_parts)

    _apply_path_guards(template_sql, slots)
    _validate_slot_guards(slots, param_map, source_path)

    program = InterpolationProgram(
        segments=tuple(segments),
        slots=tuple(slots),
        template_sql=template_sql,
    )
    return program


def render_interpolated_sql(
    program: InterpolationProgram,
    params: Mapping[str, object],
    *,
    param_specs: Sequence[ParameterSpec],
    config: InterpolationConfig,
    route_id: str,
) -> str:
    spec_map = {spec.name: spec for spec in param_specs}
    pieces: list[str] = []
    for index, segment in enumerate(program.segments):
        pieces.append(segment)
        if index >= len(program.slots):
            continue
        slot = program.slots[index]
        spec = spec_map.get(slot.name)
        if spec is None:
            raise InterpolationError(
                f"Parameter '{slot.name}' missing from route '{route_id}' definition"
            )
        value = params.get(slot.name)
        if value is None:
            raise InterpolationError(
                f"Template parameter '{slot.name}' missing for route '{route_id}'"
            )
        rendered = _apply_policy_and_filters(value, spec, slot, route_id)
        pieces.append(rendered)
    sql = "".join(pieces)
    if config.forbid_db_params_in_file_functions:
        _ensure_no_db_params_in_file_calls(sql, route_id)
    return sql


def serialize_program(program: InterpolationProgram | None) -> Mapping[str, object] | None:
    if program is None or (not program.segments and not program.slots):
        return None
    return {
        "segments": list(program.segments),
        "slots": [
            {
                "name": slot.name,
                "filters": list(slot.filters),
                "expr": slot.expr,
                "line": slot.line,
                "column": slot.column,
                "requires_path_guard": slot.requires_path_guard,
            }
            for slot in program.slots
        ],
        "template_sql": program.template_sql,
    }
def deserialize_program(
    data: Mapping[str, object] | None
) -> InterpolationProgram | None:
    if not data:
        return None
    segments = tuple(str(part) for part in data.get("segments", []))
    if not segments:
        segments = ("",)
    slots_data = data.get("slots") or []
    slots: list[InterpolationSlot] = []
    for raw in slots_data:
        if not isinstance(raw, Mapping):
            continue
        slots.append(
            InterpolationSlot(
                name=str(raw.get("name")),
                filters=tuple(str(item) for item in raw.get("filters", [])),
                expr=str(raw.get("expr", "")),
                line=int(raw.get("line", 1)),
                column=int(raw.get("column", 1)),
                requires_path_guard=bool(raw.get("requires_path_guard", False)),
            )
        )
    template_sql = str(data.get("template_sql", ""))
    return InterpolationProgram(
        segments=segments,
        slots=tuple(slots),
        template_sql=template_sql,
    )


def _slot_marker(index: int) -> str:
    return f"__wd_slot_{index}__"


def _parse_slot(
    expr: str,
    params: Mapping[str, ParameterSpec],
    position: int,
    sql: str,
    source_path: Path,
) -> InterpolationSlot:
    base, *filters = [part.strip() for part in expr.split("|")]
    if not base:
        raise _compile_error(
            f"Empty interpolation expression in {source_path} near position {position}"
        )
    if not _IDENTIFIER_PATTERN.match(base):
        raise _compile_error(
            f"Interpolation expression '{expr}' uses invalid identifier in {source_path}"
        )
    spec = params.get(base)
    if spec is None:
        raise _compile_error(
            f"Interpolation references unknown parameter '{base}' in {source_path}"
        )
    if not spec.template_only:
        raise _compile_error(
            f"Parameter '{base}' must set template_only=true to be used with '{{{{ }}}}' in {source_path}"
        )
    for filter_name in filters:
        if filter_name and filter_name.lower() not in _FILTERS:
            raise _compile_error(
                f"Filter '{filter_name}' is not supported for parameter '{base}' in {source_path}"
            )
    line, column = _offset_to_position(sql, position)
    return InterpolationSlot(
        name=base,
        filters=tuple(filter_name for filter_name in filters if filter_name),
        expr=expr,
        line=line,
        column=column,
    )


def _offset_to_position(sql: str, offset: int) -> tuple[int, int]:
    preceding = sql[:offset]
    line = preceding.count("\n") + 1
    try:
        last_newline = preceding.rindex("\n")
    except ValueError:
        column = offset + 1
    else:
        column = offset - last_newline
    return line, column


def _apply_path_guards(template_sql: str, slots: Sequence[InterpolationSlot]) -> None:
    for index, slot in enumerate(slots):
        marker = _slot_marker(index)
        position = template_sql.find(marker)
        if position == -1:
            continue
        prefix = template_sql[:position]
        open_paren = prefix.rfind("(")
        if open_paren == -1:
            continue
        func_segment = prefix[:open_paren].rstrip()
        match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*$", func_segment)
        if not match:
            continue
        func_name = match.group(1).lower()
        if func_name in _FILE_FUNCTIONS:
            slot.requires_path_guard = True


def _validate_slot_guards(
    slots: Sequence[InterpolationSlot],
    params: Mapping[str, ParameterSpec],
    source_path: Path,
) -> None:
    for slot in slots:
        spec = params.get(slot.name)
        if spec is None:
            continue
        if not slot.requires_path_guard:
            continue
        guard = spec.guard or {}
        mode = str(guard.get("mode", "")).lower()
        if mode != "path":
            raise _compile_error(
                f"Parameter '{spec.name}' must declare guard.mode='path' when used in file access within {source_path}"
            )


def _apply_policy_and_filters(
    value: object,
    spec: ParameterSpec,
    slot: InterpolationSlot,
    route_id: str,
) -> str:
    policy = str((spec.template or {}).get("policy", "literal")).lower()
    if policy not in _FILTERS:
        raise InterpolationError(
            f"Parameter '{spec.name}' uses unsupported template policy '{policy}' in route '{route_id}'"
        )
    current = _FILTERS[policy](value, spec, route_id)
    for filter_name in slot.filters:
        lowered = filter_name.lower()
        func = _FILTERS.get(lowered)
        if func is None:
            raise InterpolationError(
                f"Filter '{filter_name}' is not available for parameter '{spec.name}' in route '{route_id}'"
            )
        current = func(current, spec, route_id)
    if spec.guard and str(spec.guard.get("mode", "")).lower() == "path":
        _validate_path_value(current, spec, route_id)
    return current


def _validate_path_value(rendered: object, spec: ParameterSpec, route_id: str) -> None:
    text = str(rendered)
    normalized = text.strip("'")
    if ".." in normalized or normalized.startswith("/"):
        raise InterpolationError(
            f"Parameter '{spec.name}' produced unsafe path '{normalized}' for route '{route_id}'"
        )


def _ensure_no_db_params_in_file_calls(sql: str, route_id: str) -> None:
    for match in _FILE_FUNCTION_PATTERN.finditer(sql):
        args = match.group("args") or ""
        if "$" in args:
            func_name = match.group(1)
            raise InterpolationError(
                f"Route '{route_id}' cannot pass database parameters to {func_name}()"
            )


def _filter_literal(value: object, spec: ParameterSpec, route_id: str) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    escaped = text.replace("'", "''")
    return f"'{escaped}'"


def _filter_identifier(value: object, spec: ParameterSpec, route_id: str) -> str:
    text = str(value)
    if not _IDENTIFIER_PATTERN.match(text):
        raise InterpolationError(
            f"Parameter '{spec.name}' value '{text}' is not a valid identifier in route '{route_id}'"
        )
    return text


def _filter_raw(value: object, spec: ParameterSpec, route_id: str) -> str:
    return str(value)


_FILTERS: Mapping[str, callable[[object, ParameterSpec, str], str]] = {
    "literal": _filter_literal,
    "identifier": _filter_identifier,
    "raw": _filter_raw,
}


def _compile_error(message: str) -> RuntimeError:
    from .compiler import RouteCompilationError  # Imported lazily to avoid cycles

    return RouteCompilationError(message)


__all__ = [
    "InterpolationError",
    "InterpolationProgram",
    "InterpolationSlot",
    "build_interpolation_program",
    "render_interpolated_sql",
    "serialize_program",
    "deserialize_program",
]

