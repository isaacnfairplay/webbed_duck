"""Lazy-imported utilities shared across the test suite."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Dict

__all__ = ["duckdb", "storage"]

_MODULE_MAP: Dict[str, str] = {
    "duckdb": "tests.utils.duckdb",
    "storage": "tests.utils.storage",
}


def __getattr__(name: str) -> ModuleType:
    try:
        module_path = _MODULE_MAP[name]
    except KeyError as exc:  # pragma: no cover - defensive path
        raise AttributeError(f"module 'tests.utils' has no attribute {name!r}") from exc

    module = import_module(module_path)
    globals()[name] = module
    return module


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__))
