"""Pagination helpers for server-rendered views."""
from __future__ import annotations

import html
from typing import Mapping


def render_summary(row_count: int, pagination: Mapping[str, object] | None, rpc_payload: Mapping[str, object] | None) -> str:
    total_rows = None
    offset_value = 0
    limit_value = None
    if rpc_payload:
        total_rows = rpc_payload.get("total_rows")
        offset_value = int(rpc_payload.get("offset", 0) or 0)
        limit_raw = rpc_payload.get("limit")
        if limit_raw not in (None, ""):
            try:
                limit_value = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit_value = None
    if pagination:
        offset_raw = pagination.get("offset")
        limit_raw = pagination.get("limit")
        if offset_raw not in (None, ""):
            try:
                offset_value = int(offset_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                offset_value = offset_value
        if limit_raw not in (None, "") and limit_value is None:
            try:
                limit_value = int(limit_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit_value = None
    if total_rows in (None, ""):
        return ""
    start = offset_value + 1 if row_count else offset_value
    end = offset_value + row_count
    total = int(total_rows)
    summary = f"Showing {start:,}–{end:,} of {total:,} rows"
    next_link = None
    if rpc_payload and rpc_payload.get("next_href"):
        next_link = str(rpc_payload["next_href"])
    pagination_html = (
        f"<div class='pagination'><a href='{html.escape(next_link)}'>Next page</a></div>"
        if next_link
        else ""
    )
    return (
        f"<p class='result-summary'>{html.escape(summary)}</p>"
        + pagination_html
    )


__all__ = ["render_summary"]
