"""Plugin registries for assets and charts."""

from .assets import register_image_getter, resolve_image
from .charts import register_chart_renderer

__all__ = ["register_image_getter", "register_chart_renderer", "resolve_image"]
