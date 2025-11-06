"""Preprocess pipeline for route execution."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping, Sequence
import sys

from ..core.routes import RouteDefinition

try:  # pragma: no cover - optional dependency for type checking
    from fastapi import Request
except ModuleNotFoundError:  # pragma: no cover - fallback when FastAPI not installed
    Request = Any  # type: ignore


@dataclass(slots=True)
class PreprocessContext:
    """Context passed to preprocessors."""

    route: RouteDefinition
    request: Request | None
    options: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CallableSpec:
    """Normalized reference to a preprocess callable."""

    name: str
    module: str | None
    path: str | None
    module_alias_consumed: bool = False
    path_alias_consumed: bool = False

    @property
    def cache_key(self) -> str:
        module_part = self.module or ""
        path_part = self.path or ""
        return f"module:{module_part}|path:{path_part}|name:{self.name}"

    def describe(self) -> str:
        if self.path:
            return f"{self.path}:{self.name}"
        if self.module:
            return f"{self.module}:{self.name}"
        return self.name


_CACHE: dict[str, Callable[..., Mapping[str, Any] | None]] = {}


def run_preprocessors(
    steps: Sequence[Mapping[str, Any]],
    params: Mapping[str, Any],
    *,
    route: RouteDefinition,
    request: Request | None,
) -> dict[str, Any]:
    """Run the configured preprocessors for ``route``."""

    current: dict[str, Any] = dict(params)
    for step in steps:
        spec = extract_callable_spec(step)
        options_obj = step.get("options") if isinstance(step.get("options"), Mapping) else None
        excluded_keys = {
            "callable",
            "callable_module",
            "callable_name",
            "callable_path",
            "name",
            "options",
        }
        if spec.module_alias_consumed:
            excluded_keys.add("module")
        if spec.path_alias_consumed:
            excluded_keys.add("path")
        options = {k: v for k, v in step.items() if k not in excluded_keys}
        if options_obj:
            options.update(dict(options_obj))
        func = _load_callable(spec)
        context = PreprocessContext(route=route, request=request, options=options)
        updated = _invoke(func, current, context, options)
        if updated is None:
            continue
        if not isinstance(updated, Mapping):
            raise TypeError(
                f"Preprocessor '{spec.describe()}' must return a mapping or None, received {type(updated)!r}"
            )
        current = dict(updated)
    return current


def _invoke(
    func: Callable[..., Mapping[str, Any] | None],
    params: Mapping[str, Any],
    context: PreprocessContext,
    options: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    payload = dict(options)
    try:
        return func(dict(params), context=context, **payload)
    except TypeError as first_error:
        try:
            return func(dict(params), context, **payload)
        except TypeError:
            try:
                return func(dict(params), **payload)
            except TypeError as final_error:
                raise final_error from first_error


def _load_callable(spec: CallableSpec) -> Callable[..., Mapping[str, Any] | None]:
    cache_key = spec.cache_key
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    module = _import_callable_module(spec)
    attr = spec.name
    try:
        target = getattr(module, attr)
    except AttributeError as error:
        target = _load_attribute_from_package(module, attr)
        if target is None:
            raise error
    if not callable(target):
        raise TypeError(f"Preprocessor '{spec.describe()}' is not callable")
    _CACHE[cache_key] = target
    return target


def _import_callable_module(spec: CallableSpec) -> ModuleType:
    if spec.path:
        return _load_module_from_path(spec.path)
    if spec.module:
        return import_module(spec.module)
    raise RuntimeError("Preprocess callable is missing a module or path reference")


def _load_module_from_path(module_reference: str) -> ModuleType:
    file_path = Path(module_reference)
    if not file_path.exists():
        raise ModuleNotFoundError(f"Preprocessor module '{module_reference}' was not found")

    is_directory = file_path.is_dir()
    if is_directory:
        init_file = file_path / "__init__.py"
        if not init_file.exists():
            raise ModuleNotFoundError(
                f"Preprocessor module reference '{module_reference}' points to a directory without an __init__.py"
            )
        load_target = init_file
    else:
        load_target = file_path

    if load_target.suffix != ".py":
        raise ModuleNotFoundError(
            f"Preprocessor module reference '{module_reference}' must point to a Python file"
        )

    cache_key = f"webbed_duck.preprocess.path::{file_path}"
    if cache_key in sys.modules:
        return sys.modules[cache_key]

    search_locations = [str(file_path)] if is_directory else None
    spec = spec_from_file_location(
        cache_key,
        str(load_target),
        submodule_search_locations=search_locations,
    )
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(
            f"Could not load preprocessor module from '{module_reference}'"
        )
    module = module_from_spec(spec)
    sys.modules[cache_key] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _load_attribute_from_package(
    module: ModuleType, attr: str
) -> Callable[..., Mapping[str, Any] | None] | None:
    """Attempt to load ``attr`` from a sibling module within ``module``'s package."""

    spec = getattr(module, "__spec__", None)
    search_locations: list[str] = []
    if spec is not None and spec.submodule_search_locations:
        search_locations.extend(spec.submodule_search_locations)
    else:
        module_file = getattr(module, "__file__", None)
        if module_file:
            search_locations.append(str(Path(module_file).parent))

    for location in search_locations:
        candidate = Path(location) / f"{attr}.py"
        if not candidate.exists():
            continue
        try:
            submodule = _load_module_from_path(str(candidate))
        except ModuleNotFoundError:
            continue
        try:
            target = getattr(submodule, attr)
        except AttributeError:
            continue
        if callable(target):
            return target
    return None


def extract_callable_spec(step: Mapping[str, Any]) -> CallableSpec:
    """Normalize ``step`` into a :class:`CallableSpec`.

    Accepts both the new ``callable_*`` fields and legacy ``callable``/``name``/``path``
    spellings. Raises :class:`RuntimeError` for malformed entries.
    """

    if not isinstance(step, Mapping):
        raise RuntimeError("Preprocess step configuration must be a mapping")

    raw_name = _string_or_none(step.get("callable_name"))
    raw_module = _string_or_none(step.get("callable_module"))
    raw_path = _string_or_none(step.get("callable_path"))

    module_alias = _string_or_none(step.get("module"))
    path_alias = _string_or_none(step.get("path"))

    legacy_name = _string_or_none(step.get("name"))
    legacy_callable = _string_or_none(step.get("callable"))

    module_alias_consumed = False
    path_alias_consumed = False

    if path_alias:
        if _looks_like_filesystem_reference(path_alias):
            if not raw_path:
                raw_path = path_alias
                path_alias_consumed = True
        else:
            legacy_callable = legacy_callable or path_alias
    if legacy_name and not raw_name and not legacy_callable:
        legacy_callable = legacy_callable or legacy_name

    if legacy_callable:
        module_ref, attr = _split_legacy_reference(legacy_callable)
        raw_name = raw_name or attr
        if not raw_module and not raw_path:
            if _looks_like_filesystem_reference(module_ref):
                raw_path = module_ref
            else:
                raw_module = module_ref
    elif not raw_module and not raw_path and module_alias:
        raw_module = module_alias
        module_alias_consumed = True

    if not raw_name:
        raise RuntimeError("Preprocess step is missing 'callable_name'")

    if raw_module and raw_path:
        raise RuntimeError(
            "Preprocess step must specify only one of 'callable_module' or 'callable_path'"
        )

    if not raw_module and not raw_path:
        raise RuntimeError(
            "Preprocess step must provide either 'callable_module' or 'callable_path'"
        )

    normalized_path: str | None = None
    if raw_path:
        path_value = Path(raw_path).expanduser()
        if not path_value.is_absolute():
            path_value = (Path.cwd() / path_value).resolve()
        normalized_path = str(path_value)

    return CallableSpec(
        name=raw_name,
        module=raw_module,
        path=normalized_path,
        module_alias_consumed=module_alias_consumed,
        path_alias_consumed=path_alias_consumed,
    )


def validate_preprocess_step(step: Mapping[str, Any] | CallableSpec) -> CallableSpec:
    """Ensure that ``step`` references a loadable callable."""

    if isinstance(step, CallableSpec):
        spec = step
    else:
        spec = extract_callable_spec(step)
    _load_callable(spec)
    return spec


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _split_legacy_reference(value: str) -> tuple[str, str]:
    module_name, sep, attr = value.rpartition(":")
    if sep:
        if not attr.strip():
            raise RuntimeError(
                f"Preprocess reference '{value}' is missing a callable attribute"
            )
        return module_name, attr.strip()
    if "." in value:
        module_name, attr = value.rsplit(".", 1)
        if not attr.strip():
            raise RuntimeError(
                f"Preprocess reference '{value}' is missing a callable attribute"
            )
        return module_name, attr.strip()
    raise RuntimeError(
        "Legacy preprocess references must include ':' or '.' to separate module and attribute"
    )


def _looks_like_filesystem_reference(value: str) -> bool:
    return value.endswith(".py") or any(sep in value for sep in ("/", "\\"))


__all__ = [
    "CallableSpec",
    "PreprocessContext",
    "extract_callable_spec",
    "run_preprocessors",
    "validate_preprocess_step",
]
