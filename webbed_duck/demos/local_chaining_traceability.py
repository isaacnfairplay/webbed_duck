"""Helpers used by the local chaining traceability demo."""

from __future__ import annotations

from typing import Mapping

from webbed_duck.server.preprocess import PreprocessContext


def inject_prefix(params: Mapping[str, object], *, context: PreprocessContext, delimiter: str = "-", prefix_length: int = 2):
    """Populate the ``prefix`` parameter from the incoming barcode.

    The local chaining demo passes ``barcode`` only. This helper derives the
    uppercase prefix so the SQL route can bind it when calling
    ``traceability_prefix_map`` via ``[[uses]]``.
    """

    barcode_raw = str(params.get("barcode") or "").strip()
    if not barcode_raw:
        raise ValueError("barcode parameter is required to resolve traceability routes")
    head = barcode_raw.split(delimiter)[0]
    prefix = head[:prefix_length].upper() if head else ""
    if not prefix:
        raise ValueError("Unable to derive a prefix from the provided barcode")
    updated = dict(params)
    updated["prefix"] = prefix
    return updated


__all__ = ["inject_prefix"]
