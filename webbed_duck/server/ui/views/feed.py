"""Grouped feed view rendering."""
from __future__ import annotations

import datetime as dt
import html
from typing import Mapping, Sequence


def render_feed(
    records: Sequence[Mapping[str, object]],
    *,
    timestamp_field: str,
    title_field: str,
    summary_field: str | None,
) -> str:
    groups: dict[str, list[str]] = {"Today": [], "Yesterday": [], "Earlier": []}
    now = dt.datetime.now(dt.timezone.utc)
    for record in records:
        ts_value = record.get(timestamp_field)
        if isinstance(ts_value, str):
            try:
                ts = dt.datetime.fromisoformat(ts_value)
            except ValueError:
                ts = now
        elif isinstance(ts_value, dt.datetime):
            ts = ts_value
        else:
            ts = now
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        delta = now.date() - ts.astimezone(dt.timezone.utc).date()
        if delta.days == 0:
            bucket = "Today"
        elif delta.days == 1:
            bucket = "Yesterday"
        else:
            bucket = "Earlier"
        title = html.escape(str(record.get(title_field, "")))
        summary = (
            html.escape(str(record.get(summary_field, ""))) if summary_field else ""
        )
        entry = (
            f"<article><h4>{title}</h4>"
            + (f"<p>{summary}</p>" if summary else "")
            + f"<time>{ts.isoformat()}</time></article>"
        )
        groups[bucket].append(entry)

    sections = []
    for bucket, entries in groups.items():
        if not entries:
            continue
        sections.append(f"<section><h3>{bucket}</h3>{''.join(entries)}</section>")
    return "<div class='wd-surface wd-feed'>" + "".join(sections) + "</div>"


__all__ = ["render_feed"]
