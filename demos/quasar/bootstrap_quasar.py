"""Bootstrap utilities for the Quasar visualization demos."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from .dependencies import DependencyStatus, discover_dependencies
from .fixtures import Fixture, build_fixtures
from .notebook_builder import build_notebook
from .renderers import RendererRegistry, build_quasar_renderers


@dataclass(frozen=True)
class BootstrapArtifacts:
    """Container describing the results of a bootstrap run."""

    registry: RendererRegistry
    fixtures: Dict[str, Fixture]
    notebook_path: Path
    dependency_report: Dict[str, DependencyStatus]

    def describe(self) -> str:
        """Provide a short human-readable summary string."""

        renderers = ", ".join(sorted(self.registry.as_dict().keys()))
        fixtures = ", ".join(sorted(self.fixtures.keys()))
        return (
            "Renderers: "
            + (renderers or "(none)")
            + "; Fixtures: "
            + (fixtures or "(none)")
        )


def bootstrap_quasar(base_dir: Path | None = None) -> BootstrapArtifacts:
    """Build chart renderers, fixtures, and a demo notebook."""

    target_dir = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent
    dependency_report = discover_dependencies(["plotly", "altair"])
    registry = build_quasar_renderers(dependency_report)
    fixtures = build_fixtures()
    notebook_path = build_notebook(target_dir / "notebooks", registry, fixtures)
    return BootstrapArtifacts(
        registry=registry,
        fixtures=fixtures,
        notebook_path=notebook_path,
        dependency_report=dependency_report,
    )
