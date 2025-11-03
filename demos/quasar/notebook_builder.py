"""Generate a ready-to-use Jupyter notebook for the Quasar demo."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .fixtures import Fixture
from .renderers import RendererRegistry


_NOTEBOOK_NAME = "quasar_demo.ipynb"


def build_notebook(directory: Path, registry: RendererRegistry, fixtures: Dict[str, Fixture]) -> Path:
    """Create or update the demo notebook.

    The notebook contains Markdown/Code cells that highlight the
    registered renderers, available fixtures, and dependency status.
    The function writes an idempotent notebook so repeated bootstrap
    calls do not introduce noisy diffs.
    """

    directory.mkdir(parents=True, exist_ok=True)
    notebook_path = directory / _NOTEBOOK_NAME
    payload = _render_notebook_payload(registry, fixtures)
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    if notebook_path.exists():
        current = notebook_path.read_text(encoding="utf-8")
        if current == encoded:
            return notebook_path
    notebook_path.write_text(encoded + "\n", encoding="utf-8")
    return notebook_path


def _render_notebook_payload(registry: RendererRegistry, fixtures: Dict[str, Fixture]) -> Dict[str, object]:
    fixture_names = list(fixtures.keys())
    renderer_names = list(registry.as_dict().keys())
    dependency_rows = [
        {
            "name": renderer_name,
            "available": renderer.dependency.available,
            "version": renderer.dependency.version,
        }
        for renderer_name, renderer in registry.items()
    ]
    return {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# Quasar Visualization Demo\n",
                    "This notebook showcases generated fixtures and renderer metadata.\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "from demos.quasar.bootstrap_quasar import bootstrap_quasar\n",
                    "artifacts = bootstrap_quasar()\n",
                    "artifacts.registry.as_dict()\n",
                ],
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Available fixtures\n",
                    ", ".join(fixture_names) + "\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "artifact_rows = {name: fixture.generate()[:3] for name, fixture in artifacts.fixtures.items()}\n",
                    "artifact_rows\n",
                ],
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Renderer dependencies\n",
                    "Below is a quick look at whether Plotly/Altair are installed.\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "artifacts.dependency_report\n",
                ],
            },
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "quasar": {
                "fixtures": fixture_names,
                "renderers": renderer_names,
                "dependencies": dependency_rows,
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
