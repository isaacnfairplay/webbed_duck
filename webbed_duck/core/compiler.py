"""Compiler for Markdown + SQL routes."""
from __future__ import annotations

import pprint
import re
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

from .routes import ParameterSpec, ParameterType, RouteDefinition

FRONTMATTER_DELIMITER = "+++"
SQL_BLOCK_PATTERN = re.compile(r"```sql\s*(?P<sql>.*?)```", re.DOTALL | re.IGNORECASE)
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class RouteCompilationError(RuntimeError):
    """Raised when a route file cannot be compiled."""


try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib  # type: ignore


def compile_routes(source_dir: str | Path, build_dir: str | Path) -> List[RouteDefinition]:
    """Compile all ``*.sql.md`` files from ``source_dir`` into ``build_dir``."""

    src = Path(source_dir)
    dest = Path(build_dir)
    if not src.exists():
        raise FileNotFoundError(f"Route source directory not found: {src}")
    dest.mkdir(parents=True, exist_ok=True)

    compiled: List[RouteDefinition] = []
    for path in sorted(src.rglob("*.sql.md")):
        definition = compile_route_file(path)
        compiled.append(definition)
        _write_route_module(definition, path, src, dest)
    return compiled


def compile_route_file(path: str | Path) -> RouteDefinition:
    """Compile a single Markdown route file into a :class:`RouteDefinition`."""

    text = Path(path).read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)
    metadata_raw = _parse_frontmatter(frontmatter)
    sql = _extract_sql(body)
    params = _parse_params(metadata_raw.get("params", {}))
    param_order, prepared_sql = _prepare_sql(sql, params)

    methods = metadata_raw.get("methods") or ["GET"]
    if not isinstance(methods, Iterable) or isinstance(methods, (str, bytes)):
        raise RouteCompilationError("'methods' must be a list of HTTP methods")

    metadata = _extract_metadata(metadata_raw)

    return RouteDefinition(
        id=str(metadata_raw["id"]),
        path=str(metadata_raw["path"]),
        methods=list(methods),
        raw_sql=sql,
        prepared_sql=prepared_sql,
        param_order=param_order,
        params=params,
        title=metadata_raw.get("title"),
        description=metadata_raw.get("description"),
        metadata=metadata,
    )


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.lstrip().startswith(FRONTMATTER_DELIMITER):
        raise RouteCompilationError("Route files must begin with TOML frontmatter delimited by +++")
    first = text.find(FRONTMATTER_DELIMITER)
    second = text.find(FRONTMATTER_DELIMITER, first + len(FRONTMATTER_DELIMITER))
    if second == -1:
        raise RouteCompilationError("Unterminated frontmatter block")
    frontmatter = text[first + len(FRONTMATTER_DELIMITER):second].strip()
    body = text[second + len(FRONTMATTER_DELIMITER):]
    return frontmatter, body


def _parse_frontmatter(frontmatter: str) -> Mapping[str, object]:
    if not frontmatter:
        raise RouteCompilationError("Frontmatter block cannot be empty")
    try:
        return tomllib.loads(frontmatter)
    except Exception as exc:  # pragma: no cover - toml parsing errors vary
        raise RouteCompilationError(f"Invalid TOML frontmatter: {exc}") from exc


def _extract_sql(body: str) -> str:
    match = SQL_BLOCK_PATTERN.search(body)
    if not match:
        raise RouteCompilationError("No SQL code block found in route file")
    return match.group("sql").strip()


def _parse_params(raw: Mapping[str, object]) -> List[ParameterSpec]:
    params: List[ParameterSpec] = []
    for name, value in raw.items():
        if not isinstance(value, Mapping):
            raise RouteCompilationError(f"Parameter '{name}' must be a table of settings")
        param_type = ParameterType.from_string(str(value.get("type", "str")))
        params.append(
            ParameterSpec(
                name=name,
                type=param_type,
                required=bool(value.get("required", False)),
                default=value.get("default"),
                description=value.get("description"),
            )
        )
    return params


def _prepare_sql(sql: str, params: Sequence[ParameterSpec]) -> tuple[List[str], str]:
    param_names = {p.name for p in params}
    order: List[str] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        if name not in param_names:
            raise RouteCompilationError(f"Parameter '{{{name}}}' used in SQL but not declared in frontmatter")
        order.append(name)
        return "?"

    prepared_sql = PLACEHOLDER_PATTERN.sub(replace, sql)
    return order, prepared_sql


def _extract_metadata(metadata: Mapping[str, object]) -> Mapping[str, object]:
    reserved = {"id", "path", "methods", "params", "title", "description"}
    extras: Dict[str, object] = {}
    for key, value in metadata.items():
        if key in reserved:
            continue
        extras[key] = value
    return extras


def _write_route_module(definition: RouteDefinition, source_path: Path, src_root: Path, build_root: Path) -> None:
    relative = source_path.relative_to(src_root)
    target_rel = Path(str(relative)[: -len(".sql.md")])
    target_path = build_root / target_rel.with_suffix(".py")
    target_path.parent.mkdir(parents=True, exist_ok=True)

    route_dict: Dict[str, object] = {
        "id": definition.id,
        "path": definition.path,
        "methods": list(definition.methods),
        "raw_sql": definition.raw_sql,
        "prepared_sql": definition.prepared_sql,
        "param_order": list(definition.param_order),
        "params": [
            {
                "name": spec.name,
                "type": spec.type.value,
                "required": spec.required,
                "default": spec.default,
                "description": spec.description,
            }
            for spec in definition.params
        ],
        "title": definition.title,
        "description": definition.description,
        "metadata": dict(definition.metadata or {}),
    }

    module_content = "# Generated by webbed_duck.core.compiler\nROUTE = " + pprint.pformat(route_dict, width=88) + "\n"
    target_path.write_text(module_content, encoding="utf-8")


__all__ = [
    "compile_route_file",
    "compile_routes",
    "RouteCompilationError",
]
