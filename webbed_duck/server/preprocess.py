# TODO[todo-server-pre-s3-p7q8]: Replace legacy preprocessors with the Step 3 registry and builtin helpers when available.
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from ..core.routes import RouteDefinition
from ..plugins.loader import (
    PluginLoadError,
    PluginLoader,
    normalize_callable_name,
    normalize_plugin_path,
)

try:  # pragma: no cover - optional dependency for type checking
    from fastapi import Request
except ModuleNotFoundError:  # pragma: no cover - fallback when FastAPI not installed
    Request = Any  # type: ignore[misc,assignment]


@dataclass(slots=True)
class PreprocessContext:
    """Context passed to preprocessors."""

    route: RouteDefinition
    request: Request | None
    options: Mapping[str, Any]


class PreprocessConfigurationError(ValueError):
    """Raised when a preprocess callable reference cannot be resolved."""


@dataclass(frozen=True)
class CallableReference:
    """Normalized reference to a preprocess callable."""

    path: str
    name: str

    def describe(self) -> str:
        return f"'{self.path}:{self.name}'"


def run_preprocessors(
    steps: Sequence[Mapping[str, Any]],
    params: Mapping[str, Any],
    *,
    route: RouteDefinition,
    request: Request | None,
    loader: PluginLoader,
) -> dict[str, Any]:
    """Run the configured preprocessors for ``route``."""

    current: dict[str, Any] = dict(params)
    for step in steps:
        reference = resolve_callable_reference(step)
        func = load_preprocess_callable(reference, loader)
        options = _collect_options(step)
        context = PreprocessContext(route=route, request=request, options=options)
        updated = _invoke(func, current, context, options)
        if updated is None:
            continue
        if not isinstance(updated, Mapping):
            raise TypeError(
                f"Preprocessor '{reference.name}' must return a mapping or None, received {type(updated)!r}"
            )
        current = dict(updated)
    return current


def _collect_options(step: Mapping[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    raw_kwargs = step.get("kwargs")
    if raw_kwargs is not None:
        if not isinstance(raw_kwargs, Mapping):
            raise PreprocessConfigurationError("'kwargs' must be a table of arguments")
        options.update({str(k): v for k, v in raw_kwargs.items()})
    for key, value in step.items():
        if key in {"callable_path", "callable_name", "kwargs"}:
            continue
        options[str(key)] = value
    return options


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
    reference: CallableReference, loader: PluginLoader
) -> Callable[..., Mapping[str, Any] | None]:
    """Resolve and cache the callable described by ``reference``."""

    try:
        target = loader.load_callable(reference.path, reference.name)
    except PluginLoadError as exc:
        raise PreprocessConfigurationError(str(exc)) from exc
    return target


def resolve_callable_reference(step: Mapping[str, Any]) -> CallableReference:
    """Normalize ``step`` into a :class:`CallableReference`."""

    for legacy_key in ("callable", "callable_module", "module", "path", "name"):
        if legacy_key in step:
            raise PreprocessConfigurationError(
                "Module-based plugins are disabled. Use 'callable_path' + 'callable_name'."
            )

    if "callable_path" not in step or "callable_name" not in step:
        raise PreprocessConfigurationError(
            "Preprocess step must define both 'callable_path' and 'callable_name'."
        )

    try:
        path = normalize_plugin_path(step["callable_path"])
    except PluginLoadError as exc:
        raise PreprocessConfigurationError(str(exc)) from exc

    try:
        name = normalize_callable_name(step["callable_name"])
    except PluginLoadError as exc:
        raise PreprocessConfigurationError(str(exc)) from exc

    return CallableReference(path=path, name=name)


__all__ = [
    "CallableReference",
    "PreprocessConfigurationError",
    "PreprocessContext",
    "load_preprocess_callable",
    "resolve_callable_reference",
    "run_preprocessors",
]
