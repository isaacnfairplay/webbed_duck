"""Helpers for transforming Arrow tables into HTTP-ready payloads."""
from __future__ import annotations

import datetime as dt
import html
from typing import Iterable, Mapping, Sequence

import pyarrow as pa

from ..config import Config
from ..core.routes import ParameterSpec, ParameterType
from ..plugins.assets import resolve_image


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
    *,
    postprocess: Mapping[str, object] | None = None,
    watermark: str | None = None,
    params: Sequence[ParameterSpec] | None = None,
    param_values: Mapping[str, object] | None = None,
    format_hint: str | None = None,
) -> str:
    headers = table.column_names
    records = table_to_records(table)
    table_meta = _merge_view_metadata(route_metadata, "html_t", postprocess)
    params_html = _render_params_ui(
        table_meta, params, param_values, format_hint=format_hint
    )
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
    watermark_html = (
        f"<div class='watermark'>{html.escape(watermark)}</div>" if watermark else ""
    )
    styles = (
        "body{font-family:system-ui,sans-serif;margin:1.5rem;}"
        "table{border-collapse:collapse;width:100%;}"
        "th,td{border:1px solid #e5e7eb;padding:0.5rem;text-align:left;}"
        "tr:nth-child(even){background:#f9fafb;}"
        ".cards{display:grid;gap:1rem;}"
        f"{_PARAMS_STYLES}"
        ".banner.warning{color:#b91c1c;}"
        ".banner.info{color:#2563eb;}"
        ".watermark{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%) rotate(-24deg);"
        "font-size:3.5rem;color:rgba(37,99,235,0.12);letter-spacing:0.2rem;pointer-events:none;user-select:none;}"
    )
    return (
        "<html><head><style>"
        + styles
        + "</style></head><body>"
        + watermark_html
        + "".join(banners)
        + chart_html
        + params_html
        + f"<table><thead><tr>{header_html}</tr></thead><tbody>{rows_html}</tbody></table>"
        + "</body></html>"
    )


def render_cards_html(
    table: pa.Table,
    route_metadata: Mapping[str, object] | None,
    config: Config,
    charts: Sequence[Mapping[str, str]] | None = None,
    *,
    params: Sequence[ParameterSpec] | None = None,
    param_values: Mapping[str, object] | None = None,
    postprocess: Mapping[str, object] | None = None,
    format_hint: str | None = None,
) -> str:
    return render_cards_html_with_assets(
        table,
        route_metadata,
        config,
        charts=charts,
        postprocess=postprocess,
        assets=None,
        route_id="",
        params=params,
        param_values=param_values,
        format_hint=format_hint,
    )


def render_cards_html_with_assets(
    table: pa.Table,
    route_metadata: Mapping[str, object] | None,
    config: Config,
    *,
    charts: Sequence[Mapping[str, str]] | None = None,
    postprocess: Mapping[str, object] | None = None,
    assets: Mapping[str, object] | None = None,
    route_id: str,
    watermark: str | None = None,
    params: Sequence[ParameterSpec] | None = None,
    param_values: Mapping[str, object] | None = None,
    format_hint: str | None = None,
) -> str:
    metadata = route_metadata or {}
    cards_meta: dict[str, object] = {}
    base_cards = metadata.get("html_c")
    if isinstance(base_cards, Mapping):
        cards_meta.update(base_cards)
    if isinstance(postprocess, Mapping):
        cards_meta.update(postprocess)
    title_col = str(cards_meta.get("title_col") or (table.column_names[0] if table.column_names else "title"))
    image_col = cards_meta.get("image_col")
    meta_cols = cards_meta.get("meta_cols")
    if not isinstance(meta_cols, Sequence):
        meta_cols = [col for col in table.column_names if col not in {title_col, image_col}][:3]

    records = table_to_records(table)
    params_html = _render_params_ui(
        cards_meta, params, param_values, format_hint=format_hint
    )
    getter_name = str(assets.get("image_getter")) if assets and assets.get("image_getter") else None
    base_path = str(assets.get("base_path")) if assets and assets.get("base_path") else None
    cards = []
    for record in records:
        title = html.escape(str(record.get(title_col, "")))
        meta_items = "".join(
            f"<li><span>{html.escape(str(col))}</span>: {html.escape(str(record.get(col, '')))}</li>"
            for col in meta_cols
        )
        image_html = ""
        if image_col and record.get(image_col):
            image_value = str(record[image_col])
            if base_path and not image_value.startswith(("/", "http://", "https://")):
                image_value = f"{base_path.rstrip('/')}/{image_value}"
            resolved = resolve_image(image_value, route_id, getter_name=getter_name)
            image_html = f"<img src='{html.escape(resolved)}' alt='{title}'/>"
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
    watermark_html = (
        f"<div class='watermark'>{html.escape(watermark)}</div>" if watermark else ""
    )
    styles = (
        "body{font-family:system-ui,sans-serif;margin:1.5rem;}"
        ".cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1.25rem;}"
        ".card{border:1px solid #e5e7eb;border-radius:0.5rem;padding:1rem;background:#fff;box-shadow:0 1px 2px rgba(15,23,42,.08);}"
        ".card img{width:100%;height:160px;object-fit:cover;border-radius:0.5rem;}"
        ".card h3{margin:0.5rem 0;font-size:1.1rem;}"
        ".card ul{margin:0;padding-left:1rem;}"
        f"{_PARAMS_STYLES}"
        ".banner.info{color:#2563eb;}"
        ".watermark{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%) rotate(-24deg);"
        "font-size:3.5rem;color:rgba(37,99,235,0.12);letter-spacing:0.2rem;pointer-events:none;user-select:none;}"
    )
    return (
        "<html><head><style>"
        + styles
        + "</style></head><body>"
        + watermark_html
        + banners
        + chart_html
        + params_html
        + f"<section class='cards'>{''.join(cards)}</section>"
        + "</body></html>"
    )


_PARAMS_STYLES = (
    ".params-bar{margin-bottom:1.25rem;padding:0.85rem 1rem;border:1px solid #e5e7eb;"
    "border-radius:0.75rem;background:#f9fafb;}"
    ".params-form{display:flex;flex-wrap:wrap;gap:0.75rem;align-items:flex-end;}"
    ".param-field{display:flex;flex-direction:column;gap:0.35rem;min-width:12rem;}"
    ".param-field label{font-size:0.85rem;font-weight:600;color:#374151;}"
    ".param-field input,.param-field select{padding:0.45rem 0.6rem;border:1px solid #d1d5db;"
    "border-radius:0.375rem;font:inherit;background:#fff;min-height:2.25rem;}"
    ".param-field select{min-width:10rem;}"
    ".param-help{font-size:0.75rem;color:#6b7280;margin:0;}"
    ".param-actions{display:flex;align-items:center;gap:0.75rem;}"
    ".param-actions button{padding:0.45rem 0.95rem;border-radius:0.375rem;border:1px solid #2563eb;"
    "background:#2563eb;color:#fff;font:inherit;cursor:pointer;}"
    ".param-actions button:hover{background:#1d4ed8;border-color:#1d4ed8;}"
    ".param-actions .reset-link{color:#2563eb;text-decoration:none;font-size:0.9rem;}"
    ".param-actions .reset-link:hover{text-decoration:underline;}"
)


def _merge_view_metadata(
    route_metadata: Mapping[str, object] | None,
    view_key: str,
    postprocess: Mapping[str, object] | None,
) -> dict[str, object]:
    merged: dict[str, object] = {}
    if route_metadata and isinstance(route_metadata.get(view_key), Mapping):
        merged.update(route_metadata[view_key])  # type: ignore[arg-type]
    if isinstance(postprocess, Mapping):
        merged.update(postprocess)
    return merged


def _render_params_ui(
    view_meta: Mapping[str, object] | None,
    params: Sequence[ParameterSpec] | None,
    param_values: Mapping[str, object] | None,
    *,
    format_hint: str | None = None,
) -> str:
    if not params:
        return ""
    show: list[str] = []
    if view_meta:
        raw = view_meta.get("show_params")
        if isinstance(raw, str):
            show = [item.strip() for item in raw.split(",") if item.strip()]
        elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            show = [str(name) for name in raw]
    if not show:
        return ""
    param_map = {spec.name: spec for spec in params}
    selected_specs = [param_map[name] for name in show if name in param_map]
    if not selected_specs:
        return ""
    values = dict(param_values or {})
    show_set = {spec.name for spec in selected_specs}
    hidden_inputs = []
    format_value = values.get("format") or format_hint
    if format_value:
        hidden_inputs.append(
            "<input type='hidden' name='format' value='"
            + html.escape(_stringify_param_value(format_value))
            + "'/>"
        )
        values.pop("format", None)
    for name, value in values.items():
        if name in show_set:
            continue
        if value in {None, ""}:
            continue
        hidden_inputs.append(
            "<input type='hidden' name='"
            + html.escape(name)
            + "' value='"
            + html.escape(_stringify_param_value(value))
            + "'/>"
        )

    fields: list[str] = []
    for spec in selected_specs:
        control = str(spec.extra.get("ui_control", "")).lower()
        if control not in {"input", "select"}:
            continue
        label = str(spec.extra.get("ui_label") or spec.name.replace("_", " ").title())
        value = values.get(spec.name, spec.default)
        value_str = _stringify_param_value(value)
        field_html = ["<div class='param-field'>"]
        field_html.append(
            "<label for='param-"
            + html.escape(spec.name)
            + "'>"
            + html.escape(label)
            + "</label>"
        )
        if control == "input":
            input_type, extra_attrs = _input_attrs_for_spec(spec)
            placeholder = spec.extra.get("ui_placeholder")
            placeholder_attr = (
                " placeholder='" + html.escape(str(placeholder)) + "'" if placeholder else ""
            )
            field_html.append(
                "<input type='"
                + input_type
                + "' id='param-"
                + html.escape(spec.name)
                + "' name='"
                + html.escape(spec.name)
                + "' value='"
                + html.escape(value_str)
                + "'"
                + extra_attrs
                + placeholder_attr
                + "/>"
            )
        elif control == "select":
            options = _normalize_options(spec.extra.get("options"))
            field_html.append(
                "<select id='param-"
                + html.escape(spec.name)
                + "' name='"
                + html.escape(spec.name)
                + "'>"
            )
            if not options:
                options = [("", "")]
            for opt_value, opt_label in options:
                selected = " selected" if opt_value == value_str else ""
                field_html.append(
                    "<option value='"
                    + html.escape(opt_value)
                    + "'"
                    + selected
                    + ">"
                    + html.escape(opt_label)
                    + "</option>"
                )
            field_html.append("</select>")
        help_text = (
            spec.extra.get("ui_help")
            or spec.extra.get("ui_hint")
            or spec.description
        )
        if help_text:
            field_html.append(
                "<p class='param-help'>" + html.escape(str(help_text)) + "</p>"
            )
        field_html.append("</div>")
        fields.append("".join(field_html))

    if not fields:
        return ""

    form_html = ["<div class='params-bar'><form method='get' class='params-form'>"]
    form_html.extend(hidden_inputs)
    form_html.extend(fields)
    form_html.append(
        "<div class='param-actions'><button type='submit'>Apply</button><a class='reset-link' href='?'>Reset</a></div>"
    )
    form_html.append("</form></div>")
    return "".join(form_html)


def _input_attrs_for_spec(spec: ParameterSpec) -> tuple[str, str]:
    if spec.type is ParameterType.INTEGER:
        return "number", ""
    if spec.type is ParameterType.FLOAT:
        return "number", " step='any'"
    if spec.type is ParameterType.BOOLEAN:
        return "text", ""
    return "text", ""


def _normalize_options(options: object) -> list[tuple[str, str]]:
    normalized: list[tuple[str, str]] = []
    if isinstance(options, Mapping):
        for value, label in options.items():
            normalized.append((
                _stringify_param_value(value),
                str(label) if label is not None else "",
            ))
    elif isinstance(options, Iterable) and not isinstance(options, (str, bytes)):
        for item in options:
            if isinstance(item, Mapping):
                value = item.get("value")
                label = item.get("label", value)
                normalized.append((
                    _stringify_param_value(value),
                    str(label) if label is not None else "",
                ))
            else:
                normalized.append((
                    _stringify_param_value(item),
                    _stringify_param_value(item),
                ))
    return normalized


def _stringify_param_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def render_feed_html(
    table: pa.Table,
    route_metadata: Mapping[str, object] | None,
    config: Config,
    *,
    postprocess: Mapping[str, object] | None = None,
) -> str:
    metadata = route_metadata or {}
    feed_meta = metadata.get("feed", {})
    if not isinstance(feed_meta, Mapping):
        feed_meta = {}
    if isinstance(postprocess, Mapping):
        merged = dict(feed_meta)
        merged.update(postprocess)
        feed_meta = merged
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
    "render_cards_html_with_assets",
    "render_feed_html",
    "render_table_html",
    "table_to_records",
]
