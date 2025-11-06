"""Preprocess pipeline for route execution."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ..core.routes import RouteDefinition
from .callable_loader import (
    CallableDescriptor,
    CallableResolutionError,
    descriptor_from_legacy_reference,
    load_callable,
)

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
        options_obj = step.get("options") if isinstance(step.get("options"), Mapping) else None
        options = {
            k: v
            for k, v in step.items()
            if k
            not in {
                "callable",
                "options",
                "name",
                "path",
                "callable_name",
                "callable_source",
                "callable_source_type",
                "callable_resolved_path",
                "callable_module",
                "callable_path",
            }
        }
        if options_obj:
            options.update(dict(options_obj))
        func = _load_callable(step, callable_path)
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


def _load_callable(
    step: Mapping[str, Any], legacy_reference: str
) -> Callable[..., Mapping[str, Any] | None]:
    descriptor = _descriptor_from_step(step, legacy_reference)
    cache_key = descriptor.cache_key()
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    target = load_callable(descriptor)
    if not callable(target):
        raise TypeError(f"Preprocessor '{descriptor.name}' is not callable")
    _CACHE[cache_key] = target
    return target


def _descriptor_from_step(
    step: Mapping[str, Any], legacy_reference: str
) -> CallableDescriptor:
    name = step.get("callable_name")
    source_type = step.get("callable_source_type")
    resolved_path = step.get("callable_resolved_path")
    source_value = step.get("callable_source") or step.get("callable_module") or step.get("callable_path")

    if name and source_type and resolved_path:
        descriptor = CallableDescriptor(
            name=str(name),
            source_type=str(source_type),
            source_value=str(source_value or resolved_path),
            resolved_path=Path(str(resolved_path)),
            module_name=str(step.get("callable_module")) if step.get("callable_module") else None,
        )
        return descriptor

    if not legacy_reference:
        raise RuntimeError("Preprocess step is missing a callable reference")
    try:
        return descriptor_from_legacy_reference(legacy_reference, base_dir=None)
    except CallableResolutionError as error:
        raise RuntimeError(str(error)) from error


__all__ = ["PreprocessContext", "run_preprocessors"]
