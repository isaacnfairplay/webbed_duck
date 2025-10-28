"""Compiler for Markdown + SQL routes."""
from __future__ import annotations

import json
import pprint
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

from .routes import (
    ParameterSpec,
    ParameterType,
    RouteDefinition,
    RouteDirective,
    RouteUse,
)

FRONTMATTER_DELIMITER = "+++"
SQL_BLOCK_PATTERN = re.compile(r"```sql\s*(?P<sql>.*?)```", re.DOTALL | re.IGNORECASE)
PLACEHOLDER_PATTERN = re.compile(
    r"\{\{\s*(?P<brace>[a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}|\$(?P<dollar>[a-zA-Z_][a-zA-Z0-9_]*)"
)
DIRECTIVE_PATTERN = re.compile(r"<!--\s*@(?P<name>[a-zA-Z0-9_.:-]+)(?P<body>.*?)-->", re.DOTALL)

_KNOWN_FRONTMATTER_KEYS = {
    "append",
    "assets",
    "cache",
    "charts",
    "cache-mode",
    "cache_mode",
    "default-format",
    "default_format",
    "description",
    "feed",
    "html_c",
    "html_t",
    "id",
    "json",
    "meta",
    "methods",
    "params",
    "path",
    "postprocess",
    "preprocess",
    "returns",
    "share",
    "table",
    "title",
    "version",
    "overrides",
    "allowed_formats",
    "allowed-formats",
    "uses",
}


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
    cache: Mapping[str, object] | None
    cache_mode: str
    returns: str
    uses: Sequence[RouteUse]


@dataclass(slots=True)
class _RouteSource:
    toml_path: Path
    sql_path: Path
    doc_path: Path | None


def compile_routes(source_dir: str | Path, build_dir: str | Path) -> List[RouteDefinition]:
    """Compile all route source files from ``source_dir`` into ``build_dir``."""

    src = Path(source_dir)
    dest = Path(build_dir)
    if not src.exists():
        raise FileNotFoundError(f"Route source directory not found: {src}")
    dest.mkdir(parents=True, exist_ok=True)

    compiled: List[RouteDefinition] = []
    for source in _iter_route_sources(src):
        text = _compose_route_text(source)
        definition = compile_route_text(text, source_path=source.toml_path)
        compiled.append(definition)
        _write_route_module(definition, source.toml_path, src, dest)
    return compiled


def compile_route_file(path: str | Path) -> RouteDefinition:
    """Compile a single TOML/SQL sidecar into a :class:`RouteDefinition`."""

    toml_path = Path(path)
    if toml_path.suffix != ".toml":
        raise RouteCompilationError("compile_route_file expects a .toml metadata path")

    sql_path = toml_path.with_suffix(".sql")
    if not sql_path.exists():
        raise FileNotFoundError(f"Missing SQL file for {toml_path}")

    doc_path = toml_path.with_suffix(".md")
    doc_text = doc_path.read_text(encoding="utf-8").strip() if doc_path.exists() else ""

    toml_text = toml_path.read_text(encoding="utf-8").strip()
    sql_text = sql_path.read_text(encoding="utf-8").strip()

    parts: list[str] = []
    if doc_text:
        parts.append(doc_text)
    parts.append(f"```sql\n{sql_text}\n```")
    body = "\n\n".join(parts)
    text = f"{FRONTMATTER_DELIMITER}\n{toml_text}\n{FRONTMATTER_DELIMITER}\n\n{body}\n"
    return compile_route_text(text, source_path=toml_path)


def compile_route_text(text: str, *, source_path: Path) -> RouteDefinition:
    """Compile ``text`` into a :class:`RouteDefinition`."""

    frontmatter, body = _split_frontmatter(text)
    metadata_raw = dict(_parse_frontmatter(frontmatter))
    if "id" not in metadata_raw:
        metadata_raw["id"] = _derive_route_id(source_path)
    if "path" not in metadata_raw:
        metadata_raw["path"] = f"/{metadata_raw['id']}"
    _warn_unexpected_frontmatter(metadata_raw, source_path)
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
    if sections.cache:
        metadata["cache"] = sections.cache

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
        cache_mode=sections.cache_mode,
        returns=sections.returns,
        uses=sections.uses,
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


def _warn_unexpected_frontmatter(metadata: Mapping[str, object], path: str | Path) -> None:
    unexpected: list[str] = []
    for key in metadata.keys():
        normalized = str(key)
        if normalized not in _KNOWN_FRONTMATTER_KEYS:
            unexpected.append(normalized)
    if not unexpected:
        return
    joined = ", ".join(sorted(unexpected))
    print(
        f"[webbed-duck] Warning: unexpected frontmatter key(s) {joined} in {path}",
        file=sys.stderr,
    )


def _extract_sql(body: str) -> str:
    match = SQL_BLOCK_PATTERN.search(body)
    if not match:
        raise RouteCompilationError("No SQL code block found in route file")
    return match.group("sql").strip()


def _parse_params(raw: Mapping[str, object]) -> List[ParameterSpec]:
    params: List[ParameterSpec] = []
    for name, value in raw.items():
        if not isinstance(value, Mapping):
            if isinstance(value, str):
                params.append(
                    ParameterSpec(
                        name=name,
                        type=ParameterType.STRING,
                        required=False,
                        default=None,
                        description=None,
                        extra={"duckdb_type": value},
                    )
                )
                continue
            raise RouteCompilationError(f"Parameter '{name}' must be a table of settings")
        extras = {k: v for k, v in value.items()}
        type_value = extras.pop("type", "str")
        required_value = extras.pop("required", False)
        default_value = extras.pop("default", None)
        description_value = extras.pop("description", None)
        duckdb_type = extras.get("duckdb_type")
        param_type = ParameterType.from_string(str(type_value))
        if duckdb_type is not None:
            extras.setdefault("duckdb_type", duckdb_type)
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
        name = match.group("brace") or match.group("dollar")
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
    cache_meta = _build_cache(metadata, directives)
    cache_mode_raw = metadata_raw.get("cache_mode") or metadata_raw.get("cache-mode")
    cache_mode = str(cache_mode_raw).lower() if cache_mode_raw else "materialize"
    returns_raw = metadata_raw.get("returns")
    returns = str(returns_raw).lower() if returns_raw else "relation"
    uses = _build_uses(metadata_raw.get("uses"))

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
        cache=cache_meta,
        cache_mode=cache_mode,
        returns=returns,
        uses=uses,
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
            else:
                params[str(name)] = {"duckdb_type": settings}
    return params


def _merge_param_payload(target: MutableMapping[str, dict[str, object]], payload: Any) -> None:
    if isinstance(payload, Mapping):
        for name, value in payload.items():
            bucket = target.setdefault(str(name), {})
            if isinstance(value, Mapping):
                bucket.update({str(k): v for k, v in value.items()})
            else:
                key = "duckdb_type" if isinstance(value, str) else "default"
                bucket[key] = value
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


def _build_uses(data: object) -> list[RouteUse]:
    if isinstance(data, Mapping):
        entries: Sequence[Mapping[str, object]] = [dict(data)]
    elif isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        entries = [dict(item) for item in data if isinstance(item, Mapping)]
    else:
        return []

    uses: list[RouteUse] = []
    for entry in entries:
        alias = entry.get("alias")
        call = entry.get("call")
        if alias is None or call is None:
            raise RouteCompilationError("Each [[uses]] entry must define 'alias' and 'call'")
        mode_raw = entry.get("mode", "relation")
        mode = str(mode_raw).lower()
        args_raw = entry.get("args")
        if isinstance(args_raw, Mapping):
            args = {str(k): v for k, v in args_raw.items()}
        else:
            args = {}
        uses.append(RouteUse(alias=str(alias), call=str(call), mode=mode, args=args))
    return uses


def _build_cache(
    metadata: Mapping[str, Any], directives: Sequence[RouteDirective]
) -> Mapping[str, object] | None:
    cache_meta: dict[str, object] = {}
    base = metadata.get("cache")
    if isinstance(base, Mapping):
        cache_meta.update({str(k): v for k, v in base.items()})
    for payload in _collect_directive_payloads(directives, "cache"):
        if isinstance(payload, Mapping):
            cache_meta.update({str(k): v for k, v in payload.items()})
        elif isinstance(payload, str):
            cache_meta["profile"] = payload
    if not cache_meta:
        return None

    if "order-by" in cache_meta and "order_by" not in cache_meta:
        cache_meta["order_by"] = cache_meta.pop("order-by")

    if "order_by" in cache_meta:
        cache_meta["order_by"] = _normalize_order_by(cache_meta["order_by"])

    enabled_raw = cache_meta.get("enabled")
    enabled = True if enabled_raw is None else bool(enabled_raw)
    order_values = cache_meta.get("order_by")
    if enabled and (not isinstance(order_values, Sequence) or not order_values):
        raise RouteCompilationError(
            "[cache] blocks must define order_by = [\"column\"] when caching is enabled"
        )

    return cache_meta


def _normalize_order_by(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = [segment.strip() for segment in raw.split(",")]
        values = [part for part in parts if part]
        if not values:
            raise RouteCompilationError("cache.order_by must list at least one column name")
        return values
    if isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray)):
        values: list[str] = []
        for item in raw:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                values.append(text)
        if not values:
            raise RouteCompilationError("cache.order_by must list at least one column name")
        return values
    raise RouteCompilationError("cache.order_by must be a string or list of column names")


def _iter_route_sources(root: Path) -> list[_RouteSource]:
    sources: list[_RouteSource] = []
    seen: set[Path] = set()
    for toml_path in sorted(root.rglob("*.toml")):
        if not toml_path.is_file():
            continue
        sql_path = toml_path.with_suffix(".sql")
        if not sql_path.exists():
            continue
        doc_path = toml_path.with_suffix(".md")
        if not doc_path.exists():
            doc_path = None
        sources.append(_RouteSource(toml_path=toml_path, sql_path=sql_path, doc_path=doc_path))
        seen.add(sql_path.resolve())

    unmatched: list[Path] = []
    for sql_path in sorted(root.rglob("*.sql")):
        if not sql_path.is_file():
            continue
        if sql_path.resolve() in seen:
            continue
        toml_candidate = sql_path.with_suffix(".toml")
        if toml_candidate.exists():
            continue
        try:
            relative = sql_path.relative_to(root)
        except ValueError:
            continue
        unmatched.append(relative)
    if unmatched:
        missing = ", ".join(str(path) for path in unmatched)
        raise RouteCompilationError(f"Found SQL files without matching TOML: {missing}")

    sources.sort(key=lambda item: str(item.toml_path.relative_to(root)))
    return sources


def _compose_route_text(source: _RouteSource) -> str:
    toml_text = source.toml_path.read_text(encoding="utf-8").strip()
    sql_text = source.sql_path.read_text(encoding="utf-8").strip()
    parts: list[str] = []
    if source.doc_path is not None:
        doc_text = source.doc_path.read_text(encoding="utf-8").strip()
        if doc_text:
            parts.append(doc_text)
    parts.append(f"```sql\n{sql_text}\n```")
    body = "\n\n".join(parts)
    return f"{FRONTMATTER_DELIMITER}\n{toml_text}\n{FRONTMATTER_DELIMITER}\n\n{body}\n"


def _derive_route_id(path: Path) -> str:
    name = path.name
    if path.suffix:
        name = path.stem
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", name)
    name = name.strip("_")
    return name or "route"


def _target_module_path(relative: Path) -> Path:
    if relative.suffix == ".toml":
        return relative.with_suffix(".py")
    raise RouteCompilationError(f"Unsupported route source path: {relative}")


def _write_route_module(definition: RouteDefinition, source_path: Path, src_root: Path, build_root: Path) -> None:
    relative = source_path.relative_to(src_root)
    target_path = build_root / _target_module_path(relative)
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
        "cache_mode": definition.cache_mode,
        "returns": definition.returns,
        "uses": [
            {
                "alias": use.alias,
                "call": use.call,
                "mode": use.mode,
                **({"args": dict(use.args)} if use.args else {}),
            }
            for use in definition.uses
        ],
    }

    module_content = "# Generated by webbed_duck.core.compiler\nROUTE = " + pprint.pformat(route_dict, width=88) + "\n"
    target_path.write_text(module_content, encoding="utf-8")


__all__ = [
    "compile_route_file",
    "compile_route_text",
    "compile_routes",
    "RouteCompilationError",
]
