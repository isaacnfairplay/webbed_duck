"""Utilities for describing optional visualization dependencies."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib.util import find_spec
from typing import Dict, Iterable, Optional


@dataclass(frozen=True)
class DependencyStatus:
    """Information about the availability of an optional dependency."""

    name: str
    available: bool
    version: Optional[str]

    @property
    def summary(self) -> str:
        """Return a human readable status summary."""
        if self.available:
            return f"{self.name} {self.version or 'unknown version'} available"
        return f"{self.name} not installed"


def probe_dependency(name: str) -> DependencyStatus:
    """Return availability metadata for ``name``.

    The function avoids importing optional dependencies when they are
    missing, but it will perform a lightweight import when present to
    retrieve a version string.
    """

    spec = find_spec(name)
    if spec is None:
        return DependencyStatus(name=name, available=False, version=None)
    module = import_module(name)
    version = getattr(module, "__version__", None)
    return DependencyStatus(name=name, available=True, version=version)


def discover_dependencies(names: Iterable[str]) -> Dict[str, DependencyStatus]:
    """Collect dependency metadata for ``names``.

    Parameters
    ----------
    names:
        Dependency names to probe using :func:`probe_dependency`.
    """

    return {name: probe_dependency(name) for name in names}
