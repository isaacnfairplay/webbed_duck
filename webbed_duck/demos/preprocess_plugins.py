"""Reusable preprocess helpers showcased in the demos."""
from __future__ import annotations

from typing import Mapping

from ..server.preprocess import PreprocessContext


def append_suffix(
    params: Mapping[str, object],
    *,
    context: PreprocessContext,
    source: str = "input",
    target: str = "processed",
    suffix: str = "-module",
) -> Mapping[str, object]:
    """Append ``suffix`` to ``params[source]`` and store the result in ``target``."""

    updated = dict(params)
    value = str(updated.get(source, ""))
    updated[target] = f"{value}{suffix}"
    return updated


__all__ = ["append_suffix"]
