"""Route definitions and helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from importlib import util
from pathlib import Path
from types import ModuleType
import datetime as _dt
import decimal
from typing import Any, List, Mapping, Sequence


class ParameterType(str, Enum):
    STRING = "str"
    INTEGER = "int"
    FLOAT = "float"
    BOOLEAN = "bool"

    @classmethod
    def from_string(cls, value: str) -> "ParameterType":
        try:
            return cls(value)
        except ValueError as exc:  # pragma: no cover - defensive programming
            raise ValueError(f"Unsupported parameter type: {value!r}") from exc


@dataclass(slots=True)
class ParameterSpec:
    name: str
    type: ParameterType = ParameterType.STRING
    required: bool = False
    default: Any | None = None
    description: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def convert(self, raw: str) -> Any:
        if self.type is ParameterType.STRING:
            return raw
        if self.type is ParameterType.INTEGER:
            return int(raw)
        if self.type is ParameterType.FLOAT:
            return float(raw)
        if self.type is ParameterType.BOOLEAN:
            normalized = raw.strip()
            lowered = normalized.lower()
            if lowered in {"1", "true", "t", "yes", "y"}:
                return True
            if lowered in {"0", "false", "f", "no", "n"}:
                return False
            raise ValueError(f"Cannot interpret {raw!r} as boolean")
        raise TypeError(f"Unsupported parameter type: {self.type!r}")


@dataclass(slots=True)
class RouteDirective:
    name: str
    args: Mapping[str, str]
    value: str | None = None


@dataclass(slots=True)
class RouteUse:
    alias: str
    call: str
    mode: str = "relation"
    args: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RouteDefinition:
    id: str
    path: str
    methods: Sequence[str]
    raw_sql: str
    prepared_sql: str
    param_order: Sequence[str]
    params: Sequence[ParameterSpec]
    title: str | None = None
    description: str | None = None
    metadata: Mapping[str, Any] | None = None
    directives: Sequence[RouteDirective] = ()
    version: str | None = None
    default_format: str | None = None
    allowed_formats: Sequence[str] = ()
    preprocess: Sequence[Mapping[str, Any]] = ()
    postprocess: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    charts: Sequence[Mapping[str, Any]] = ()
    assets: Mapping[str, Any] | None = None
    cache_mode: str = "materialize"
    returns: str = "relation"
    uses: Sequence[RouteUse] = ()
    constants: Mapping[str, object] = field(default_factory=dict)
    constant_params: Mapping[str, object] = field(default_factory=dict)
    constant_types: Mapping[str, str] = field(default_factory=dict)
    constant_param_types: Mapping[str, str] = field(default_factory=dict)

    def find_param(self, name: str) -> ParameterSpec | None:
        for param in self.params:
            if param.name == name:
                return param
        return None


def load_compiled_routes(build_dir: str | Path) -> List[RouteDefinition]:
    """Load compiled route manifests from ``build_dir``."""

    path = Path(build_dir)
    if not path.exists():
        raise FileNotFoundError(f"Compiled routes directory not found: {path}")

    definitions: List[RouteDefinition] = []
    for module_path in sorted(path.rglob("*.py")):
        if module_path.name == "__init__.py":
            continue
        module = _load_module_from_path(module_path)
        route_dict = getattr(module, "ROUTE", None)
        if not isinstance(route_dict, Mapping):  # pragma: no cover - guard
            continue
        definitions.append(_route_from_mapping(route_dict))
    return definitions


def _load_module_from_path(path: Path) -> ModuleType:
    spec = util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Cannot import module from {path}")
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def _route_from_mapping(route: Mapping[str, Any]) -> RouteDefinition:
    params: list[ParameterSpec] = []
    for item in route.get("params", []):
        if not isinstance(item, Mapping):
            continue
        extra = item.get("extra") if isinstance(item.get("extra"), Mapping) else {}
        params.append(
            ParameterSpec(
                name=str(item.get("name")),
                type=ParameterType.from_string(str(item.get("type", "str"))),
                required=bool(item.get("required", False)),
                default=item.get("default"),
                description=item.get("description"),
                extra=dict(extra),
            )
        )
    metadata = route.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}

    postprocess = route.get("postprocess")
    if not isinstance(postprocess, Mapping):
        postprocess = {}
    else:
        postprocess = {str(k): dict(v) for k, v in postprocess.items() if isinstance(v, Mapping)}

    assets = route.get("assets")
    if isinstance(assets, Mapping):
        assets = dict(assets)
    else:
        assets = None

    directives_data = route.get("directives", [])
    directives: list[RouteDirective] = []
    for item in directives_data:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name")) if item.get("name") is not None else ""
        if not name:
            continue
        args_map = item.get("args")
        if isinstance(args_map, Mapping):
            args = {str(k): str(v) for k, v in args_map.items()}
        else:
            args = {}
        value = item.get("value")
        directives.append(RouteDirective(name=name, args=args, value=str(value) if value is not None else None))

    uses_data = route.get("uses", [])
    uses: list[RouteUse] = []
    for item in uses_data:
        if not isinstance(item, Mapping):
            continue
        alias = item.get("alias")
        call = item.get("call")
        if not alias or not call:
            continue
        mode = str(item.get("mode", "relation")).lower()
        args_map = item.get("args")
        if isinstance(args_map, Mapping):
            args = {str(k): v for k, v in args_map.items()}
        else:
            args = {}
        uses.append(RouteUse(alias=str(alias), call=str(call), mode=mode, args=args))

    constants, constant_types = _deserialize_constant_table(route.get("constants"))

    constant_params_data = route.get("constant_params")
    if isinstance(constant_params_data, Mapping):
        constant_params: dict[str, object] = {}
        constant_param_types: dict[str, str] = {}
        for key, value in constant_params_data.items():
            placeholder = str(key)
            val, type_name = _deserialize_constant_value(placeholder, value)
            constant_params[placeholder] = val
            constant_param_types[placeholder] = type_name
    else:
        constant_params = {}
        constant_param_types = {}

    return RouteDefinition(
        id=str(route["id"]),
        path=str(route["path"]),
        methods=list(route.get("methods", ["GET"])),
        raw_sql=str(route["raw_sql"]),
        prepared_sql=str(route["prepared_sql"]),
        param_order=list(route.get("param_order", [])),
        params=params,
        title=route.get("title"),
        description=route.get("description"),
        metadata=metadata,
        directives=directives,
        version=str(route.get("version")) if route.get("version") is not None else None,
        default_format=str(route.get("default_format")) if route.get("default_format") is not None else None,
        allowed_formats=[str(item) for item in route.get("allowed_formats", [])],
        preprocess=[dict(item) if isinstance(item, Mapping) else {"callable": str(item)} for item in route.get("preprocess", [])],
        postprocess=postprocess,
        charts=[dict(item) for item in route.get("charts", []) if isinstance(item, Mapping)],
        assets=assets,
        cache_mode=str(route.get("cache_mode", "materialize")).lower(),
        returns=str(route.get("returns", "relation")).lower(),
        uses=uses,
        constants=constants,
        constant_params=constant_params,
        constant_types=constant_types,
        constant_param_types=constant_param_types,
    )


def _deserialize_constant_table(data: object) -> tuple[dict[str, object], dict[str, str]]:
    values: dict[str, object] = {}
    types: dict[str, str] = {}
    if not isinstance(data, Mapping):
        return values, types
    for name, payload in data.items():
        text_name = str(name)
        value, type_name = _deserialize_constant_value(text_name, payload)
        values[text_name] = value
        types[text_name] = type_name
    return values, types


def _deserialize_constant_value(name: str, payload: object) -> tuple[object, str]:
    if isinstance(payload, Mapping) and "value" in payload:
        raw_value = payload.get("value")
        type_name = str(payload.get("duckdb_type") or payload.get("type") or "VARCHAR").upper()
    else:
        raw_value = payload
        type_name = "VARCHAR"

    if type_name == "BOOLEAN":
        if isinstance(raw_value, bool):
            return raw_value, type_name
        if isinstance(raw_value, str):
            lowered = raw_value.strip().lower()
            if lowered in {"true", "t", "1", "yes", "y"}:
                return True, type_name
            if lowered in {"false", "f", "0", "no", "n"}:
                return False, type_name
        raise ValueError(f"Constant '{name}' payload cannot be parsed as BOOLEAN")
    if type_name == "DATE":
        if isinstance(raw_value, _dt.date) and not isinstance(raw_value, _dt.datetime):
            return raw_value, type_name
        return _dt.date.fromisoformat(str(raw_value)), type_name
    if type_name == "TIMESTAMP":
        if isinstance(raw_value, _dt.datetime):
            return raw_value, type_name
        return _dt.datetime.fromisoformat(str(raw_value)), type_name
    if type_name == "DECIMAL":
        return decimal.Decimal(str(raw_value)), type_name
    if type_name == "INTEGER":
        return int(raw_value), type_name
    if type_name == "DOUBLE":
        return float(raw_value), type_name
    if type_name == "IDENTIFIER":
        return str(raw_value), type_name
    return str(raw_value), type_name


__all__ = [
    "ParameterSpec",
    "ParameterType",
    "RouteDefinition",
    "RouteDirective",
    "RouteUse",
    "load_compiled_routes",
]
