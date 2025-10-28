"""Utilities for vendoring third-party assets at runtime."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx

from ..static.chartjs import CHARTJS_VERSION, SCRIPT_NAME

DEFAULT_CHARTJS_SOURCE: Final[str] = (
    f"https://cdn.jsdelivr.net/npm/chart.js@{CHARTJS_VERSION}/dist/{SCRIPT_NAME}"
)
CHARTJS_FILENAME: Final[str] = SCRIPT_NAME


@dataclass(slots=True)
class ChartJSVendorResult:
    """Outcome for preparing the Chart.js runtime asset."""

    prepared: bool
    error: str | None = None
    skipped: bool = False


def ensure_chartjs_vendor(
    storage_root: Path,
    *,
    source_url: str = DEFAULT_CHARTJS_SOURCE,
    timeout: float = 10.0,
) -> ChartJSVendorResult:
    """Ensure a local copy of Chart.js exists under ``storage_root``.

    Parameters
    ----------
    storage_root:
        Base storage directory for the running server instance.
    source_url:
        The URL used to fetch Chart.js when no local copy exists.
    timeout:
        Request timeout (seconds) for the vendor download.
    """

    storage_root = Path(storage_root)
    vendor_dir = storage_root / "static" / "vendor" / "chartjs"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    target = vendor_dir / CHARTJS_FILENAME
    if target.exists():
        return ChartJSVendorResult(prepared=True)

    skip_env = os.getenv("WEBDUCK_SKIP_CHARTJS_DOWNLOAD", "").lower()
    if skip_env in {"1", "true", "yes"}:
        return ChartJSVendorResult(prepared=False, error="Chart.js download skipped via environment override", skipped=True)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(source_url)
            response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network failure safety
        return ChartJSVendorResult(prepared=False, error=f"{exc}")

    try:
        target.write_bytes(response.content)
    except OSError as exc:
        return ChartJSVendorResult(prepared=False, error=f"{exc}")

    return ChartJSVendorResult(prepared=True)


__all__ = [
    "CHARTJS_FILENAME",
    "ChartJSVendorResult",
    "DEFAULT_CHARTJS_SOURCE",
    "ensure_chartjs_vendor",
]
