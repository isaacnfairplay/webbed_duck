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
        callable_path = str(step.get("callable") or "").strip()
        if not callable_path:
            raise RuntimeError("Preprocess step is missing a callable reference")
        options_obj = step.get("options") if isinstance(step.get("options"), Mapping) else None
        options = {k: v for k, v in step.items() if k not in {"callable", "options", "name", "path"}}
        if options_obj:
            options.update(dict(options_obj))
        func = _load_callable(callable_path)
        context = PreprocessContext(route=route, request=request, options=options)
        updated = _invoke(func, current, context, options)
        if updated is None:
            continue
        if not isinstance(updated, Mapping):
            raise TypeError(
                f"Preprocessor '{callable_path}' must return a mapping or None, received {type(updated)!r}"
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


def _load_callable(path: str) -> Callable[..., Mapping[str, Any] | None]:
    if path in _CACHE:
        return _CACHE[path]
    module_name, attr = _split_target(path)
    module = _import_callable_module(module_name)
    try:
        target = getattr(module, attr)
    except AttributeError as error:
        target = _load_attribute_from_package(module, attr)
        if target is None:
            raise error
    if not callable(target):
        raise TypeError(f"Preprocessor '{path}' is not callable")
    _CACHE[path] = target
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


def _import_callable_module(module_reference: str) -> ModuleType:
    module_path = Path(module_reference)
    if (
        module_path.suffix == ".py"
        or module_path.is_absolute()
        or any(sep in module_reference for sep in ("/", "\\"))
    ):
        return _load_module_from_path(module_reference)
    return import_module(module_reference)


def _load_module_from_path(module_reference: str) -> ModuleType:
    file_path = Path(module_reference).expanduser()
    if not file_path.is_absolute():
        file_path = (Path.cwd() / file_path).resolve()
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


__all__ = ["PreprocessContext", "run_preprocessors"]
