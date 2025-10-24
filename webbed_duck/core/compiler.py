"""Compiler for Markdown + SQL routes."""
from __future__ import annotations

import json
import pprint
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

from .routes import ParameterSpec, ParameterType, RouteDefinition, RouteDirective

FRONTMATTER_DELIMITER = "+++"
SQL_BLOCK_PATTERN = re.compile(r"```sql\s*(?P<sql>.*?)```", re.DOTALL | re.IGNORECASE)
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
DIRECTIVE_PATTERN = re.compile(r"<!--\s*@(?P<name>[a-zA-Z0-9_.:-]+)(?P<body>.*?)-->", re.DOTALL)


class RouteCompilationError(RuntimeError):
    """Raised when a route file cannot be compiled."""


try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib  # type: ignore


@dataclass(slots=True)
class _RouteSections:
    route_id: str
    path: str
    version: str | None
    default_format: str | None
    allowed_formats: list[str]
    params: Mapping[str, Mapping[str, object]]
    preprocess: list[Mapping[str, object]]
    postprocess: Mapping[str, Mapping[str, object]]
    charts: list[Mapping[str, object]]
    assets: Mapping[str, object] | None


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
    directives = _extract_directives(body)
    metadata = _extract_metadata(metadata_raw)
    sections = _interpret_sections(metadata_raw, directives, metadata)

    sql = _extract_sql(body)
    params = _parse_params(sections.params)
    param_order, prepared_sql = _prepare_sql(sql, params)

    methods = metadata_raw.get("methods") or ["GET"]
    if not isinstance(methods, Iterable) or isinstance(methods, (str, bytes)):
        raise RouteCompilationError("'methods' must be a list of HTTP methods")

    if sections.charts and "charts" not in metadata:
        metadata["charts"] = sections.charts
    if sections.postprocess:
        for key, value in sections.postprocess.items():
            metadata.setdefault(key, value)
    if sections.assets and "assets" not in metadata:
        metadata["assets"] = sections.assets

    return RouteDefinition(
        id=sections.route_id,
        path=sections.path,
        methods=list(methods),
        raw_sql=sql,
        prepared_sql=prepared_sql,
        param_order=param_order,
        params=params,
        title=metadata_raw.get("title"),
        description=metadata_raw.get("description"),
        metadata=metadata,
        directives=directives,
        version=sections.version,
        default_format=sections.default_format,
        allowed_formats=sections.allowed_formats,
        preprocess=sections.preprocess,
        postprocess=sections.postprocess,
        charts=sections.charts,
        assets=sections.assets,
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
        extras = {k: v for k, v in value.items()}
        type_value = extras.pop("type", "str")
        required_value = extras.pop("required", False)
        default_value = extras.pop("default", None)
        description_value = extras.pop("description", None)
        param_type = ParameterType.from_string(str(type_value))
        params.append(
            ParameterSpec(
                name=name,
                type=param_type,
                required=bool(required_value),
                default=default_value,
                description=description_value if description_value is None else str(description_value),
                extra=extras,
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


def _extract_directives(body: str) -> List[RouteDirective]:
    directives: List[RouteDirective] = []
    for match in DIRECTIVE_PATTERN.finditer(body):
        name = match.group("name").strip()
        if not name:
            continue
        raw = match.group("body").strip()
        args: Dict[str, str] = {}
        value: str | None = None
        if raw:
            if raw.startswith("{") or raw.startswith("["):
                value = raw
            else:
                try:
                    tokens = shlex.split(raw)
                except ValueError:
                    tokens = raw.split()
                positional: List[str] = []
                for token in tokens:
                    if "=" in token:
                        key, val = token.split("=", 1)
                        args[key.strip()] = val.strip()
                    else:
                        positional.append(token)
                if positional:
                    value = " ".join(positional)
        directives.append(RouteDirective(name=name, args=args, value=value))
    return directives


def _interpret_sections(
    metadata_raw: Mapping[str, Any],
    directives: Sequence[RouteDirective],
    metadata: MutableMapping[str, Any],
) -> _RouteSections:
    meta_section: dict[str, Any] = {}
    base_meta = metadata_raw.get("meta")
    if isinstance(base_meta, Mapping):
        meta_section.update({str(k): v for k, v in base_meta.items()})
    for payload in _collect_directive_payloads(directives, "meta"):
        if isinstance(payload, Mapping):
            meta_section.update({str(k): v for k, v in payload.items()})

    route_id = str(meta_section.get("id", metadata_raw["id"]))
    path = str(meta_section.get("path", metadata_raw["path"]))
    version = meta_section.get("version")
    if version is not None:
        version = str(version)

    default_format = meta_section.get("default_format") or meta_section.get("default-format")
    if default_format is None:
        default_format = metadata.get("default_format") or metadata.get("default-format")
    default_format = str(default_format).lower() if default_format else None

    allowed_formats = _normalize_string_list(
        meta_section.get("allowed_formats")
        or meta_section.get("allowed-formats")
        or metadata.get("allowed_formats")
        or metadata.get("allowed-formats")
    )

    params_map = _normalize_params(metadata_raw.get("params"))
    for payload in _collect_directive_payloads(directives, "params"):
        _merge_param_payload(params_map, payload)

    preprocess = _build_preprocess(metadata, directives)
    postprocess = _build_postprocess(metadata, directives)
    charts = _build_charts(metadata, directives)
    assets = _build_assets(metadata, directives)

    return _RouteSections(
        route_id=route_id,
        path=path,
        version=version,
        default_format=default_format,
        allowed_formats=allowed_formats,
        params=params_map,
        preprocess=preprocess,
        postprocess=postprocess,
        charts=charts,
        assets=assets,
    )


def _collect_directive_payloads(directives: Sequence[RouteDirective], name: str) -> list[Any]:
    payloads: list[Any] = []
    for directive in directives:
        if directive.name != name:
            continue
        payload = _parse_directive_payload(directive)
        if payload is not None:
            payloads.append(payload)
    return payloads


def _parse_directive_payload(directive: RouteDirective) -> Any:
    raw = (directive.value or "").strip()
    if raw:
        if raw.startswith("{") or raw.startswith("["):
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RouteCompilationError(
                    f"Directive '@{directive.name}' must contain valid JSON payload"
                ) from exc
        if not directive.args:
            return raw
    if directive.args:
        return {str(k): _coerce_value(v) for k, v in directive.args.items()}
    return None


def _coerce_value(value: str) -> object:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if lowered.startswith("0x"):
            return int(lowered, 16)
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _normalize_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[\s,]+", value.strip())
        return [part.lower() for part in parts if part]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item).lower() for item in value]
    return []


def _normalize_params(raw: object) -> dict[str, dict[str, object]]:
    params: dict[str, dict[str, object]] = {}
    if isinstance(raw, Mapping):
        for name, settings in raw.items():
            if isinstance(settings, Mapping):
                params[str(name)] = {str(k): v for k, v in settings.items()}
    return params


def _merge_param_payload(target: MutableMapping[str, dict[str, object]], payload: Any) -> None:
    if isinstance(payload, Mapping):
        for name, value in payload.items():
            bucket = target.setdefault(str(name), {})
            if isinstance(value, Mapping):
                bucket.update({str(k): v for k, v in value.items()})
            else:
                bucket["default"] = value
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        for item in payload:
            _merge_param_payload(target, item)


def _build_preprocess(
    metadata: Mapping[str, Any], directives: Sequence[RouteDirective]
) -> list[Mapping[str, object]]:
    steps: list[Mapping[str, object]] = []
    base = metadata.get("preprocess")
    steps.extend(_normalize_preprocess_entries(base))
    for payload in _collect_directive_payloads(directives, "preprocess"):
        steps.extend(_normalize_preprocess_entries(payload))
    return steps


def _normalize_preprocess_entries(data: object) -> list[Mapping[str, object]]:
    entries: list[Mapping[str, object]] = []
    if isinstance(data, Mapping):
        if any(key in data for key in ("callable", "path", "name")):
            normalized = dict(data)
            if "callable" not in normalized:
                if "name" in normalized:
                    normalized["callable"] = str(normalized.pop("name"))
                elif "path" in normalized:
                    normalized["callable"] = str(normalized.pop("path"))
            if "callable" not in normalized:
                raise RouteCompilationError("Preprocess directives must specify a callable name")
            normalized["callable"] = str(normalized["callable"])
            entries.append(normalized)
        else:
            for name, options in data.items():
                entry: dict[str, object] = {"callable": str(name)}
                if isinstance(options, Mapping):
                    entry.update(options)
                entries.append(entry)
    elif isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        for item in data:
            if isinstance(item, Mapping):
                normalized = dict(item)
                if "callable" not in normalized:
                    if "name" in normalized:
                        normalized["callable"] = str(normalized.pop("name"))
                    elif "path" in normalized:
                        normalized["callable"] = str(normalized.pop("path"))
                if "callable" not in normalized:
                    raise RouteCompilationError(
                        "Preprocess directives must specify a callable name"
                    )
                normalized["callable"] = str(normalized["callable"])
                entries.append(normalized)
            else:
                entries.append({"callable": str(item)})
    elif isinstance(data, str):
        entries.append({"callable": data})
    return entries


def _build_postprocess(
    metadata: Mapping[str, Any], directives: Sequence[RouteDirective]
) -> dict[str, dict[str, object]]:
    config: dict[str, dict[str, object]] = {}
    postprocess_block = metadata.get("postprocess")
    if isinstance(postprocess_block, Mapping):
        for fmt, options in postprocess_block.items():
            if isinstance(options, Mapping):
                config[str(fmt).lower()] = {str(k): v for k, v in options.items()}
    for fmt_key in ("html_t", "html_c", "feed", "json", "table"):
        options = metadata.get(fmt_key)
        if isinstance(options, Mapping):
            config.setdefault(fmt_key.lower(), {str(k): v for k, v in options.items()})
    for payload in _collect_directive_payloads(directives, "postprocess"):
        if isinstance(payload, Mapping):
            for fmt, options in payload.items():
                if isinstance(options, Mapping):
                    bucket = config.setdefault(str(fmt).lower(), {})
                    bucket.update({str(k): v for k, v in options.items()})
    return config


def _build_charts(
    metadata: Mapping[str, Any], directives: Sequence[RouteDirective]
) -> list[Mapping[str, object]]:
    charts: list[Mapping[str, object]] = []
    base = metadata.get("charts")
    if isinstance(base, Sequence) and not isinstance(base, (str, bytes)):
        for item in base:
            if isinstance(item, Mapping):
                charts.append(dict(item))
    for payload in _collect_directive_payloads(directives, "charts"):
        if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
            for item in payload:
                if isinstance(item, Mapping):
                    charts.append(dict(item))
        elif isinstance(payload, Mapping):
            charts.append(dict(payload))
    return charts


def _build_assets(
    metadata: Mapping[str, Any], directives: Sequence[RouteDirective]
) -> Mapping[str, object] | None:
    assets: dict[str, object] = {}
    base = metadata.get("assets")
    if isinstance(base, Mapping):
        assets.update({str(k): v for k, v in base.items()})
    for payload in _collect_directive_payloads(directives, "assets"):
        if isinstance(payload, Mapping):
            assets.update({str(k): v for k, v in payload.items()})
    return assets or None


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
                **({"extra": dict(spec.extra)} if spec.extra else {}),
            }
            for spec in definition.params
        ],
        "title": definition.title,
        "description": definition.description,
        "metadata": dict(definition.metadata or {}),
        "directives": [
            {"name": item.name, "args": dict(item.args), "value": item.value}
            for item in definition.directives
        ],
        "version": definition.version,
        "default_format": definition.default_format,
        "allowed_formats": list(definition.allowed_formats or []),
        "preprocess": [dict(item) for item in definition.preprocess],
        "postprocess": {key: dict(value) for key, value in (definition.postprocess or {}).items()},
        "charts": [dict(item) for item in definition.charts],
        "assets": dict(definition.assets) if definition.assets else None,
    }

    module_content = "# Generated by webbed_duck.core.compiler\nROUTE = " + pprint.pformat(route_dict, width=88) + "\n"
    target_path.write_text(module_content, encoding="utf-8")


__all__ = [
    "compile_route_file",
    "compile_routes",
    "RouteCompilationError",
]
