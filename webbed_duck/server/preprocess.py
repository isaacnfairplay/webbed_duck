"""Preprocess pipeline for route execution."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable, Mapping, Sequence

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
    module_name, _, attr = path.partition(":")
    if not attr:
        module_name, attr = path.rsplit(".", 1)
    module = import_module(module_name)
    target = getattr(module, attr)
    if not callable(target):
        raise TypeError(f"Preprocessor '{path}' is not callable")
    _CACHE[path] = target
    return target


__all__ = ["PreprocessContext", "run_preprocessors"]
