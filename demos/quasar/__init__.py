"""Quasar visualization demo scaffolding.

This package contains helpers for bootstrapping example
visualization tooling that relies on optional dependencies
like Plotly and Altair.  Modules intentionally avoid importing
those packages at module import time so that the demo can be
explored even when the visualization libraries are not installed.
"""

from .bootstrap_quasar import bootstrap_quasar, BootstrapArtifacts

__all__ = ["bootstrap_quasar", "BootstrapArtifacts"]
