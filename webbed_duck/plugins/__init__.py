"""Plugin registries for assets and charts."""

from .assets import (
    list_image_getters,
    register_image_getter,
    reset_image_getters,
    resolve_image,
)
from .charts import (
    get_chart_renderer,
    list_chart_renderers,
    register_chart_renderer,
    render_route_charts,
    reset_chart_renderers,
)

__all__ = [
    "register_image_getter",
    "reset_image_getters",
    "list_image_getters",
    "resolve_image",
    "register_chart_renderer",
    "reset_chart_renderers",
    "list_chart_renderers",
    "get_chart_renderer",
    "render_route_charts",
]
