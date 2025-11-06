"""Utilities for emitting consistent deprecation guidance for core modules."""

from __future__ import annotations

import warnings
from typing import Final

_ENGINE_MIGRATION_REFERENCE: Final[
    str
] = "See docs/MIGRATION.md for migration guidance and the engine roadmap."


def warn_legacy_module(module_name: str) -> None:
    """Emit a :class:`DeprecationWarning` for the given module."""

    warnings.warn(
        (
            f"{module_name} is part of the legacy webbed_duck.core surface and will "
            "be replaced by the forthcoming engine package. "
            f"{_ENGINE_MIGRATION_REFERENCE}"
        ),
        DeprecationWarning,
        stacklevel=2,
    )


def warn_legacy_entrypoint(qualified_name: str) -> None:
    """Emit a :class:`DeprecationWarning` for the given entry point."""

    warnings.warn(
        (
            f"{qualified_name} is deprecated alongside the rest of webbed_duck.core "
            "and will migrate to webbed_duck.engine. "
            f"{_ENGINE_MIGRATION_REFERENCE}"
        ),
        DeprecationWarning,
        stacklevel=2,
    )
