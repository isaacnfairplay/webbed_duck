from __future__ import annotations

import datetime as dt
import html
from typing import Iterable, Mapping, Sequence

import pyarrow as pa

from ..config import Config


def table_to_records(table: pa.Table) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in table.to_pylist():
        converted = {key: _json_friendly(value) for key, value in row.items()}
        records.append(converted)
    return records


def render_table_html(
    table: pa.Table,
    route_metadata: Mapping[str, object] | None,
    config: Config,
    charts: Sequence[Mapping[str, str]] | None = None,
) -> str:
    headers = table.column_names
    records = table_to_records(table)
    rows_html = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row.get(col, '')))}</td>" for col in headers) + "</tr>"
        for row in records
    )
    header_html = "".join(f"<th>{html.escape(col)}</th>" for col in headers)
    banners: list[str] = []
    if config.ui.show_http_warning:
        banners.append("<p class='banner warning'>Development mode – HTTP only</p>")
    if config.ui.error_taxonomy_banner:
        banners.append("<p class='banner info'>Errors follow the webbed_duck taxonomy (see docs).</p>")
    chart_html = "".join(item["html"] for item in charts or [])
    return (
        "<html><head><style>"
        "body{font-family:system-ui,sans-serif;margin:1.5rem;}"
        "table{border-collapse:collapse;width:100%;}" 
        "th,td{border:1px solid #e5e7eb;padding:0.5rem;text-align:left;}"
        "tr:nth-child(even){background:#f9fafb;}"
        ".cards{display:grid;gap:1rem;}"
        ".banner.warning{color:#b91c1c;}"
        ".banner.info{color:#2563eb;}"
        "</style></head><body>"
        + "".join(banners)
        + chart_html
        + f"<table><thead><tr>{header_html}</tr></thead><tbody>{rows_html}</tbody></table>"
        + "</body></html>"
    )


def render_cards_html(
    table: pa.Table,
    route_metadata: Mapping[str, object] | None,
    config: Config,
    charts: Sequence[Mapping[str, str]] | None = None,
) -> str:
    metadata = route_metadata or {}
    cards_meta = metadata.get("html_c", {})
    if not isinstance(cards_meta, Mapping):
        cards_meta = {}
    title_col = str(cards_meta.get("title_col") or (table.column_names[0] if table.column_names else "title"))
    image_col = cards_meta.get("image_col")
    meta_cols = cards_meta.get("meta_cols")
    if not isinstance(meta_cols, Sequence):
        meta_cols = [col for col in table.column_names if col not in {title_col, image_col}][:3]

    records = table_to_records(table)
    cards = []
    for record in records:
        title = html.escape(str(record.get(title_col, "")))
        meta_items = "".join(
            f"<li><span>{html.escape(str(col))}</span>: {html.escape(str(record.get(col, '')))}</li>"
            for col in meta_cols
        )
        image_html = ""
        if image_col and record.get(image_col):
            image_html = f"<img src='{html.escape(str(record[image_col]))}' alt='{title}'/>"
        cards.append(
            "<article class='card'>"
            + image_html
            + f"<h3>{title}</h3>"
            + f"<ul>{meta_items}</ul>"
            + "</article>"
        )
    banners = ""
    if config.ui.error_taxonomy_banner:
        banners = "<p class='banner info'>Error taxonomy: user, data, system.</p>"
    chart_html = "".join(item["html"] for item in charts or [])
    return (
        "<html><head><style>"
        "body{font-family:system-ui,sans-serif;margin:1.5rem;}"
        ".cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1.25rem;}"
        ".card{border:1px solid #e5e7eb;border-radius:0.5rem;padding:1rem;background:#fff;box-shadow:0 1px 2px rgba(15,23,42,.08);}"
        ".card img{width:100%;height:160px;object-fit:cover;border-radius:0.5rem;}"
        ".card h3{margin:0.5rem 0;font-size:1.1rem;}"
        ".card ul{margin:0;padding-left:1rem;}"
        ".banner.info{color:#2563eb;}"
        "</style></head><body>"
        + banners
        + chart_html
        + f"<section class='cards'>{''.join(cards)}</section>"
        + "</body></html>"
    )


def render_feed_html(table: pa.Table, route_metadata: Mapping[str, object] | None, config: Config) -> str:
    metadata = route_metadata or {}
    feed_meta = metadata.get("feed", {})
    if not isinstance(feed_meta, Mapping):
        feed_meta = {}
    ts_col = str(feed_meta.get("timestamp_col") or (table.column_names[0] if table.column_names else "timestamp"))
    title_col = str(feed_meta.get("title_col") or (table.column_names[1] if len(table.column_names) > 1 else "title"))
    summary_col = feed_meta.get("summary_col")

    records = table_to_records(table)
    groups: dict[str, list[str]] = {"Today": [], "Yesterday": [], "Earlier": []}
    now = dt.datetime.now(dt.timezone.utc)
    for record in records:
        ts_value = record.get(ts_col)
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
        title = html.escape(str(record.get(title_col, "")))
        summary = html.escape(str(record.get(summary_col, ""))) if summary_col else ""
        entry = f"<article><h4>{title}</h4><p>{summary}</p><time>{ts.isoformat()}</time></article>"
        groups[bucket].append(entry)

    sections = []
    for bucket, entries in groups.items():
        if not entries:
            continue
        sections.append(f"<section><h3>{bucket}</h3>{''.join(entries)}</section>")
    taxonomy = ""
    if config.ui.error_taxonomy_banner:
        taxonomy = "<aside class='banner info'>Feeds suppress sensitive system errors.</aside>"
    return (
        "<html><head><style>"
        "body{font-family:system-ui,sans-serif;margin:1.5rem;}"
        "section{margin-bottom:1.5rem;}"
        "h3{color:#111827;}"
        "article{padding:0.75rem 0;border-bottom:1px solid #e5e7eb;}"
        "time{display:block;color:#6b7280;font-size:0.875rem;}"
        ".banner.info{color:#2563eb;}"
        "</style></head><body>"
        + taxonomy
        + "".join(sections)
        + "</body></html>"
    )


def _json_friendly(value: object) -> object:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


__all__ = [
    "render_cards_html",
    "render_feed_html",
    "render_table_html",
    "table_to_records",
]
