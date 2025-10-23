"""Route definitions and helpers."""
from __future__ import annotations

from dataclasses import dataclass
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

    def convert(self, raw: str) -> Any:
        if self.type is ParameterType.STRING:
            return raw
        if self.type is ParameterType.INTEGER:
            return int(raw)
        if self.type is ParameterType.FLOAT:
            return float(raw)
        if self.type is ParameterType.BOOLEAN:
            lowered = raw.lower()
            if lowered in {"1", "true", "t", "yes", "y"}:
                return True
            if lowered in {"0", "false", "f", "no", "n"}:
                return False
            raise ValueError(f"Cannot interpret {raw!r} as boolean")
        raise TypeError(f"Unsupported parameter type: {self.type!r}")


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
    params = [
        ParameterSpec(
            name=item["name"],
            type=ParameterType.from_string(item.get("type", "str")),
            required=bool(item.get("required", False)),
            default=item.get("default"),
            description=item.get("description"),
        )
        for item in route.get("params", [])
        if isinstance(item, Mapping)
    ]
    metadata = route.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}

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
    )


__all__ = [
    "ParameterSpec",
    "ParameterType",
    "RouteDefinition",
    "load_compiled_routes",
]
