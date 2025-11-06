"""Standalone preprocess helper for the filesystem-path demo."""
from __future__ import annotations

from typing import Mapping

from webbed_duck.server.preprocess import PreprocessContext


def append_suffix_from_path(
    params: Mapping[str, object],
    *,
    context: PreprocessContext,
    source: str = "input",
    target: str = "processed",
    suffix: str = "-path",
) -> Mapping[str, object]:
    updated = dict(params)
    value = str(updated.get(source, ""))
    updated[target] = f"{value}{suffix}"
    updated.setdefault("source_file", str(context.options.get("source_file", __file__)))
    return updated


__all__ = ["append_suffix_from_path"]
