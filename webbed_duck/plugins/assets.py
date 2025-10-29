from __future__ import annotations

from typing import Callable, Dict, Mapping

ImageGetter = Callable[[str, str], str]

_REGISTRY: Dict[str, ImageGetter] = {}


def register_image_getter(name: str) -> Callable[[ImageGetter], ImageGetter]:
    """Register an image getter callback."""

    def decorator(func: ImageGetter) -> ImageGetter:
        _REGISTRY[name] = func
        return func

    return decorator


def get_image_getter(name: str) -> ImageGetter:
    """Return the registered getter for ``name``.

    When the requested getter is not installed we fall back to the
    ``static_fallback`` registration if it exists.  If neither the requested
    getter nor the fallback are present a :class:`LookupError` is raised so
    callers notice the misconfiguration instead of silently re-installing the
    default implementation.
    """

    if name in _REGISTRY:
        return _REGISTRY[name]

    fallback = _REGISTRY.get("static_fallback")
    if fallback is None:
        raise LookupError(
            f"Image getter '{name}' is not registered and no 'static_fallback' getter is available"
        )
    return fallback


def resolve_image(name: str, route_id: str, getter_name: str | None = None) -> str:
    getter = get_image_getter(getter_name or "static_fallback")
    return getter(name, route_id)


@register_image_getter("static_fallback")
def static_fallback(name: str, route_id: str) -> str:  # pragma: no cover - trivial
    return f"/static/{name}"


def list_image_getters() -> Mapping[str, ImageGetter]:
    """Return a shallow copy of the current registry."""

    return dict(_REGISTRY)


def reset_image_getters(include_defaults: bool = True) -> None:
    """Clear the registry and optionally reinstall built-in getters."""

    _REGISTRY.clear()
    if include_defaults:
        _REGISTRY["static_fallback"] = static_fallback


__all__ = [
    "register_image_getter",
    "get_image_getter",
    "resolve_image",
    "list_image_getters",
    "reset_image_getters",
]
