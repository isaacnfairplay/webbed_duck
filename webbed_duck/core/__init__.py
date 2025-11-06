"""Deprecated legacy runtime modules awaiting the ``webbed_duck.engine`` rollout."""

from ._deprecation import warn_legacy_module

warn_legacy_module(__name__)

__all__ = [
    "compiler",
    "incremental",
    "interpolation",
    "local",
    "routes",
]
