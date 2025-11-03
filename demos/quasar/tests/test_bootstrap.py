from __future__ import annotations

import json
from pathlib import Path

from demos.quasar.bootstrap_quasar import BootstrapArtifacts, bootstrap_quasar
from demos.quasar.fixtures import Fixture, preview_fixture_rows
from demos.quasar.renderers import RendererRegistry


def test_bootstrap_creates_expected_artifacts(tmp_path: Path) -> None:
    artifacts = bootstrap_quasar(tmp_path / "demo")
    assert isinstance(artifacts, BootstrapArtifacts)
    assert isinstance(artifacts.registry, RendererRegistry)
    assert set(artifacts.registry.as_dict().keys()) == {"plotly", "altair"}
    assert isinstance(artifacts.fixtures["timeseries"], Fixture)
    assert artifacts.notebook_path.exists()
    assert artifacts.notebook_path.parent == tmp_path / "demo" / "notebooks"
    assert set(artifacts.dependency_report.keys()) == {"plotly", "altair"}

    preview = preview_fixture_rows(artifacts.fixtures.values(), limit=2)
    assert set(preview.keys()) == {"timeseries", "categories"}
    assert len(preview["timeseries"]) == 2
    assert len(preview["categories"]) == 2

    rendered = artifacts.registry.get("plotly").render(preview["timeseries"])
    assert rendered["backend"] == "plotly"
    assert rendered["renderer"] == "plotly"
    assert isinstance(rendered["available"], bool)
    assert rendered["data_preview"]

    description = artifacts.describe()
    assert "plotly" in description and "categories" in description


def test_notebook_metadata_contains_registry_details(tmp_path: Path) -> None:
    artifacts = bootstrap_quasar(tmp_path / "workspace")
    payload = json.loads(artifacts.notebook_path.read_text(encoding="utf-8"))
    quasar_meta = payload["metadata"]["quasar"]
    assert set(quasar_meta["fixtures"]) == set(artifacts.fixtures.keys())
    assert set(quasar_meta["renderers"]) == set(artifacts.registry.as_dict().keys())
    dependency_names = {row["name"] for row in quasar_meta["dependencies"]}
    assert dependency_names == {"plotly", "altair"}
