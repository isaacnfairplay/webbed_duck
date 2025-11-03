"""Renderer registry for Quasar visualization demos."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping

from .dependencies import DependencyStatus, discover_dependencies

DataSeries = Iterable[Mapping[str, Any]]
RenderFunc = Callable[[DataSeries], Mapping[str, Any]]


@dataclass
class ChartRenderer:
    """Container describing how to render a particular chart."""

    name: str
    backend: str
    dependency: DependencyStatus
    render: RenderFunc


class RendererRegistry:
    """Maintain a registry of chart renderers."""

    def __init__(self) -> None:
        self._renderers: MutableMapping[str, ChartRenderer] = {}

    def register(self, renderer: ChartRenderer) -> None:
        if renderer.name in self._renderers:
            raise ValueError(f"Renderer '{renderer.name}' already registered")
        self._renderers[renderer.name] = renderer

    def get(self, name: str) -> ChartRenderer:
        return self._renderers[name]

    def items(self):
        return self._renderers.items()

    def as_dict(self) -> Dict[str, ChartRenderer]:
        return dict(self._renderers)


def _build_renderer(name: str, backend: str, dependency: DependencyStatus) -> ChartRenderer:
    """Create a renderer using the provided dependency metadata."""

    def _render(data: DataSeries) -> Mapping[str, Any]:
        data_list = list(data)
        return {
            "backend": backend,
            "renderer": name,
            "available": dependency.available,
            "dependency_version": dependency.version,
            "data_preview": data_list[:5],
        }

    return ChartRenderer(name=name, backend=backend, dependency=dependency, render=_render)


def build_quasar_renderers(
    dependencies: Dict[str, DependencyStatus] | None = None,
) -> RendererRegistry:
    """Build the default renderer registry for the demo."""

    if dependencies is None:
        dependencies = discover_dependencies(["plotly", "altair"])
    registry = RendererRegistry()
    registry.register(_build_renderer("plotly", backend="plotly", dependency=dependencies["plotly"]))
    registry.register(_build_renderer("altair", backend="altair", dependency=dependencies["altair"]))
    return registry
