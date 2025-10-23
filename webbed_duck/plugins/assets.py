from __future__ import annotations

from typing import Callable, Dict

ImageGetter = Callable[[str, str], str]

_REGISTRY: Dict[str, ImageGetter] = {}


def register_image_getter(name: str) -> Callable[[ImageGetter], ImageGetter]:
    """Register an image getter callback."""

    def decorator(func: ImageGetter) -> ImageGetter:
        _REGISTRY[name] = func
        return func

    return decorator


def get_image_getter(name: str) -> ImageGetter:
    return _REGISTRY.get(name, _REGISTRY.setdefault("static_fallback", static_fallback))


def resolve_image(name: str, route_id: str, getter_name: str | None = None) -> str:
    getter = get_image_getter(getter_name or "static_fallback")
    return getter(name, route_id)


@register_image_getter("static_fallback")
def static_fallback(name: str, route_id: str) -> str:  # pragma: no cover - trivial
    return f"/static/{name}"


__all__ = ["register_image_getter", "get_image_getter", "resolve_image"]
