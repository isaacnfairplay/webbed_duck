"""Route definitions and helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from importlib import util
from pathlib import Path
from types import ModuleType
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
    )


__all__ = [
    "ParameterSpec",
    "ParameterType",
    "RouteDefinition",
    "RouteDirective",
    "RouteUse",
    "load_compiled_routes",
]
