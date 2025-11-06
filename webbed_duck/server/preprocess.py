"""Preprocess pipeline for route execution."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib.util import find_spec, module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping, Sequence
import sys

from typing import Literal

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


_CACHE: dict[str, Callable[..., Mapping[str, Any] | None]] = {}


class PreprocessConfigurationError(ValueError):
    """Raised when a preprocess callable reference cannot be resolved."""


@dataclass(frozen=True)
class CallableReference:
    """Normalized reference to a preprocess callable."""

    source: Literal["module", "path"]
    location: str
    attribute: str
    display: str

    @property
    def cache_key(self) -> str:
        prefix = "module" if self.source == "module" else "path"
        return f"{prefix}::{self.location}:{self.attribute}"

    def describe(self) -> str:
        if self.source == "module":
            return f"module '{self.display}'"
        return f"path '{self.display}'"


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
        reference = resolve_callable_reference(step)
        options_obj = step.get("options") if isinstance(step.get("options"), Mapping) else None
        options = {
            k: v
            for k, v in step.items()
            if k
            not in {
                "callable",
                "callable_module",
                "callable_name",
                "callable_path",
                "options",
                "name",
                "path",
            }
        }
        if options_obj:
            options.update(dict(options_obj))
        func = load_preprocess_callable(reference)
        context = PreprocessContext(route=route, request=request, options=options)
        updated = _invoke(func, current, context, options)
        if updated is None:
            continue
        if not isinstance(updated, Mapping):
            raise TypeError(
                f"Preprocessor '{reference.attribute}' must return a mapping or None, received {type(updated)!r}"
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


def load_preprocess_callable(
    reference: CallableReference,
) -> Callable[..., Mapping[str, Any] | None]:
    """Resolve and cache the callable described by ``reference``."""

    cache_key = reference.cache_key
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    module = _import_callable_module(reference)
    try:
        target = getattr(module, reference.attribute)
    except AttributeError:
        target = _load_attribute_from_package(module, reference.attribute)
        if target is None:
            raise PreprocessConfigurationError(
                f"Callable '{reference.attribute}' was not found in {reference.describe()}"
            ) from None
    if not callable(target):
        raise PreprocessConfigurationError(
            f"Resolved attribute '{reference.attribute}' from {reference.describe()} is not callable"
        )
    _CACHE[cache_key] = target
    return target


def _split_target(path: str) -> tuple[str, str]:
    module_name, sep, attr = path.rpartition(":")
    if sep:
        attr = attr.strip()
        if not attr:
            raise RuntimeError(f"Preprocessor '{path}' is missing a callable attribute")
        return module_name, attr
    if "." in path:
        module_name, attr = path.rsplit(".", 1)
        if not attr:
            raise RuntimeError(f"Preprocessor '{path}' is missing a callable attribute")
        return module_name, attr
    raise RuntimeError(
        "Preprocess callable references must include a module and attribute separated by ':' or '.'"
    )


def _import_callable_module(reference: CallableReference) -> ModuleType:
    if reference.source == "path":
        return _load_module_from_path(reference.location, reference.display)

    spec = find_spec(reference.location)
    if spec is not None:
        if spec.origin and spec.origin not in {"built-in", "frozen", "namespace"}:
            return _load_module_from_path(spec.origin, reference.location)
        search_locations = list(spec.submodule_search_locations or [])
        for location in search_locations:
            candidate = Path(location) / "__init__.py"
            if candidate.exists():
                return _load_module_from_path(str(candidate), reference.location)
    return import_module(reference.location)


def _load_module_from_path(module_reference: str, display_reference: str | None = None) -> ModuleType:
    display = display_reference or module_reference
    file_path = Path(module_reference).expanduser()
    if not file_path.is_absolute():
        file_path = (Path.cwd() / file_path).resolve()
    if not file_path.exists():
        raise ModuleNotFoundError(f"Preprocessor module '{display}' was not found")

    is_directory = file_path.is_dir()
    if is_directory:
        init_file = file_path / "__init__.py"
        if not init_file.exists():
            raise ModuleNotFoundError(
                f"Preprocessor module reference '{display}' points to a directory without an __init__.py"
            )
        load_target = init_file
    else:
        load_target = file_path

    if load_target.suffix != ".py":
        raise ModuleNotFoundError(
            f"Preprocessor module reference '{display}' must point to a Python file"
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
            f"Could not load preprocessor module from '{display}'"
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
            submodule = _load_module_from_path(str(candidate), str(candidate))
        except ModuleNotFoundError:
            continue
        try:
            target = getattr(submodule, attr)
        except AttributeError:
            continue
        if callable(target):
            return target
    return None


def _looks_like_path(value: str) -> bool:
    return any(sep in value for sep in ("/", "\\")) or Path(value).suffix in {".py", ".pyc"}


def resolve_callable_reference(step: Mapping[str, Any]) -> CallableReference:
    """Normalize ``step`` into a :class:`CallableReference`."""

    explicit_module = str(step.get("callable_module") or "").strip()
    explicit_path = str(step.get("callable_path") or "").strip()
    explicit_name = str(step.get("callable_name") or "").strip()
    legacy = str(step.get("callable") or "").strip()

    module_or_path: str | None = None
    attribute: str | None = explicit_name or None

    if legacy:
        try:
            module_or_path, legacy_attr = _split_target(legacy)
        except RuntimeError as exc:
            raise PreprocessConfigurationError(str(exc)) from exc
        if not attribute:
            attribute = legacy_attr
        if not explicit_module and not explicit_path:
            if _looks_like_path(module_or_path):
                explicit_path = module_or_path
            else:
                explicit_module = module_or_path

    if explicit_module and explicit_path:
        raise PreprocessConfigurationError(
            "Preprocess step must specify either 'callable_module' or 'callable_path', not both"
        )

    if not attribute:
        raise PreprocessConfigurationError(
            "Preprocess step is missing 'callable_name'; include it explicitly or provide a legacy 'callable' reference"
        )

    if explicit_module:
        if _looks_like_path(explicit_module) or explicit_module.endswith(".py"):
            raise PreprocessConfigurationError(
                "'callable_module' must be a module path (e.g. 'pkg.module'); use 'callable_path' for filesystem references"
            )
        return CallableReference(
            source="module",
            location=explicit_module,
            attribute=attribute,
            display=explicit_module,
        )

    if explicit_path:
        resolved = Path(explicit_path).expanduser()
        if not resolved.is_absolute():
            resolved = (Path.cwd() / resolved).resolve()
        return CallableReference(
            source="path",
            location=str(resolved),
            attribute=attribute,
            display=explicit_path,
        )

    if module_or_path is not None:
        if _looks_like_path(module_or_path):
            resolved = Path(module_or_path).expanduser()
            if not resolved.is_absolute():
                resolved = (Path.cwd() / resolved).resolve()
            return CallableReference(
                source="path",
                location=str(resolved),
                attribute=attribute,
                display=module_or_path,
            )
        return CallableReference(
            source="module",
            location=module_or_path,
            attribute=attribute,
            display=module_or_path,
        )

    raise PreprocessConfigurationError(
        "Preprocess step must define either 'callable_module' or 'callable_path' (or provide a legacy 'callable' string)"
    )


__all__ = [
    "CallableReference",
    "PreprocessConfigurationError",
    "PreprocessContext",
    "load_preprocess_callable",
    "resolve_callable_reference",
    "run_preprocessors",
]
