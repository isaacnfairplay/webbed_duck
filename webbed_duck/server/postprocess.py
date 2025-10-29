"""Helpers for transforming Arrow tables into HTTP-ready payloads."""
from __future__ import annotations

import datetime as dt
import html
import json
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

import pyarrow as pa
import pyarrow.compute as pc

from ..config import Config
from ..core.routes import ParameterSpec, ParameterType
from ..plugins.assets import resolve_image
from .cache import (
    InvariantFilterSetting,
    canonicalize_invariant_value,
    normalize_invariant_value,
    parse_invariant_filters,
)
from .vendor import DEFAULT_CHARTJS_SOURCE


def table_to_records(table: pa.Table) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in table.to_pylist():
        converted = {key: _json_friendly(value) for key, value in row.items()}
        records.append(converted)
    return records


_BASE_LAYOUT_STYLES = (
    ":root{color-scheme:light dark;--wd-top-offset:0px;}"
    ":root[data-has-top='true']{--wd-top-offset:4.5rem;}"
    "body{font-family:system-ui,sans-serif;margin:0;background:#f8fafc;color:#0f172a;}"
    ".wd-shell{min-height:100vh;background:inherit;}"
    ".wd-top{position:sticky;top:0;z-index:90;background:rgba(255,255,255,0.96);backdrop-filter:blur(8px);box-shadow:0 1px 0 rgba(15,23,42,0.08);transition:transform 0.2s ease;}"
    ".wd-top[data-hidden='true']{transform:translateY(-100%);}"
    ".wd-top-inner{padding:0.75rem 1.5rem;display:flex;flex-direction:column;gap:0.75rem;}"
    ".wd-top-actions{display:flex;align-items:center;justify-content:flex-end;gap:0.5rem;flex-wrap:wrap;}"
    ".wd-top-button{appearance:none;border:1px solid #c7d2fe;background:#e0e7ff;color:#1e3a8a;border-radius:9999px;padding:0.4rem 0.95rem;font-size:0.85rem;font-weight:600;cursor:pointer;transition:background 0.2s ease,border-color 0.2s ease;}"
    ".wd-top-button:hover{background:#c7d2fe;border-color:#a5b4fc;}"
    ".wd-top[data-collapsed='true'] .wd-top-sections{display:none;}"
    ".wd-top[data-collapsed='true'] .wd-top-actions{justify-content:space-between;}"
    ".wd-top-sections{display:flex;flex-direction:column;gap:0.75rem;}"
    ".wd-banners{display:flex;flex-direction:column;gap:0.35rem;}"
    ".wd-banners .banner{margin:0;}"
    ".wd-summary{display:flex;flex-direction:column;gap:0.5rem;font-size:0.95rem;color:#1f2937;}"
    ".wd-filters .params-bar{margin:0;}"
    ".wd-filters[hidden]{display:none!important;}"
    ".wd-main{padding:calc(var(--wd-top-offset,0px) + 1.5rem) 1.5rem 2rem;transition:padding-top 0.2s ease;}"
    ".wd-main-inner{display:flex;flex-direction:column;gap:1.5rem;}"
    ".wd-chart-block{background:#fff;border-radius:0.75rem;box-shadow:0 1px 2px rgba(15,23,42,0.08);padding:1.25rem;}"
    ".wd-chart-block:empty{display:none;}"
    ".wd-surface{background:#fff;border-radius:0.75rem;box-shadow:0 1px 2px rgba(15,23,42,0.08);padding:1.25rem;}"
    ".wd-surface--flush{padding:0;overflow:hidden;}"
    ".wd-main-inner > *:empty{display:none;}"
    ".banner.warning{color:#b91c1c;}"
    ".banner.info{color:#2563eb;}"
    ".watermark{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%) rotate(-24deg);font-size:3.5rem;color:rgba(37,99,235,0.12);letter-spacing:0.2rem;pointer-events:none;user-select:none;}"
    "@media(max-width:720px){.wd-top-inner{padding:0.65rem 1rem;}.wd-main{padding:calc(var(--wd-top-offset,0px) + 1rem) 1rem 1.5rem;}}"
)


_TOP_BAR_SCRIPT = (
    "<script>(function(){"
    "var top=document.querySelector('[data-wd-top]');"
    "if(!top){return;}"
    "var root=document.documentElement;"
    "var filters=top.querySelector('[data-wd-filters]');"
    "var toggleTop=top.querySelector('[data-wd-top-toggle]');"
    "var toggleFilters=top.querySelector('[data-wd-filters-toggle]');"
    "var lastY=window.scrollY||0;"
    "function setOffset(){var hidden=top.getAttribute('data-hidden')==='true';var offset=hidden?0:top.getBoundingClientRect().height;root.style.setProperty('--wd-top-offset',offset+'px');}"
    "function ensureVisible(){top.setAttribute('data-hidden','false');setOffset();}"
    "setOffset();"
    "if(toggleFilters){if(!filters){toggleFilters.style.display='none';}else{var hideLabel=toggleFilters.dataset.hideLabel||'Hide filters';var showLabel=toggleFilters.dataset.showLabel||'Show filters';function updateFilters(){var hidden=filters.hasAttribute('hidden');toggleFilters.textContent=hidden?showLabel:hideLabel;toggleFilters.setAttribute('aria-expanded',hidden?'false':'true');}updateFilters();toggleFilters.addEventListener('click',function(){if(filters.hasAttribute('hidden')){filters.removeAttribute('hidden');}else{filters.setAttribute('hidden','');}updateFilters();setOffset();});}}"
    "if(toggleTop){var hideHead=toggleTop.dataset.hideLabel||'Hide header';var showHead=toggleTop.dataset.showLabel||'Show header';function updateTopButton(){var collapsed=top.getAttribute('data-collapsed')==='true';toggleTop.textContent=collapsed?showHead:hideHead;toggleTop.setAttribute('aria-expanded',collapsed?'false':'true');}updateTopButton();toggleTop.addEventListener('click',function(){var collapsed=top.getAttribute('data-collapsed')==='true';if(collapsed){top.setAttribute('data-collapsed','false');}else{top.setAttribute('data-collapsed','true');}top.setAttribute('data-hidden','false');updateTopButton();setOffset();});}"
    "var ticking=false;"
    "function handleScroll(){var current=window.scrollY||0;var delta=current-lastY;lastY=current;var collapsed=top.getAttribute('data-collapsed')==='true';if(collapsed){top.setAttribute('data-hidden','false');setOffset();return;}if(delta>12&&current>24){top.setAttribute('data-hidden','true');}else if(delta<-12){top.setAttribute('data-hidden','false');}setOffset();}"
    "window.addEventListener('scroll',function(){if(!ticking){window.requestAnimationFrame(function(){handleScroll();ticking=false;});ticking=true;}});"
    "window.addEventListener('resize',function(){window.requestAnimationFrame(setOffset);});"
    "top.addEventListener('mouseenter',ensureVisible);"
    "top.addEventListener('focusin',ensureVisible);"
    "document.addEventListener('keydown',function(ev){if(ev.key==='Home'){ensureVisible();}});"
    "})();</script>"
)


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
    pagination: Mapping[str, object] | None = None,
    rpc_payload: Mapping[str, object] | None = None,
    cache_meta: Mapping[str, object] | None = None,
) -> str:
    headers = table.column_names
    records = table_to_records(table)
    table_meta = _merge_view_metadata(route_metadata, "html_t", postprocess)
    params_html = _render_params_ui(
        table_meta,
        params,
        param_values,
        format_hint=format_hint,
        pagination=pagination,
        route_metadata=route_metadata,
        cache_meta=cache_meta,
        current_table=table,
    )
    summary_html = _render_summary_html(
        len(records),
        pagination,
        rpc_payload,
    )
    rpc_html = _render_rpc_payload(rpc_payload)
    rows_html = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row.get(col, '')))}</td>" for col in headers) + "</tr>"
        for row in records
    )
    header_html = "".join(f"<th>{html.escape(col)}</th>" for col in headers)
    banners: list[str] = []
    if config.ui.show_http_warning:
        banners.append("<p class='banner warning'>Development mode – HTTP only</p>")
    if config.ui.error_taxonomy_banner:
        banners.append(
            "<p class='banner info'>Errors follow the webbed_duck taxonomy (see docs).</p>"
        )
    chart_html = "".join(item["html"] for item in charts or [])
    watermark_html = _render_watermark_html(watermark)
    styles = (
        ".wd-table{overflow:hidden;}"
        ".wd-table-scroller{overflow:auto;max-width:100%;background:#fff;}"
        ".wd-table-scroller table{border-collapse:collapse;width:100%;min-width:100%;background:#fff;}"
        ".wd-table-scroller th,.wd-table-scroller td{border-bottom:1px solid #e2e8f0;padding:0.75rem 1rem;text-align:left;font-size:0.95rem;color:#1f2937;}"
        ".wd-table-scroller tbody tr:nth-child(even){background:#f8fafc;}"
        ".wd-table-scroller tbody tr:hover{background:#eef2ff;}"
        ".wd-table-scroller tbody tr:last-child td{border-bottom:none;}"
        ".wd-table-scroller thead th{position:sticky;top:calc(var(--wd-top-offset,0px));background:#e2e8f0;color:#0f172a;font-weight:600;z-index:3;}"
        ".wd-table-scroller thead th::after{content:'';position:absolute;left:0;bottom:0;width:100%;height:1px;background:#cbd5f5;}"
        f"{_PARAMS_STYLES}"
    )
    return _render_html_document(
        styles=styles,
        watermark_html=watermark_html,
        banners_html="".join(banners),
        chart_html=chart_html,
        params_html=params_html,
        summary_html=summary_html,
        content_html=(
            "<div class='wd-surface wd-surface--flush wd-table'><div class='wd-table-scroller'><table><thead><tr>"
            + header_html
            + "</tr></thead><tbody>"
            + rows_html
            + "</tbody></table></div></div>"
        ),
        rpc_html=rpc_html,
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
    pagination: Mapping[str, object] | None = None,
    rpc_payload: Mapping[str, object] | None = None,
    cache_meta: Mapping[str, object] | None = None,
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
        cards_meta,
        params,
        param_values,
        format_hint=format_hint,
        pagination=pagination,
        route_metadata=route_metadata,
        cache_meta=cache_meta,
        current_table=table,
    )
    summary_html = _render_summary_html(
        len(records),
        pagination,
        rpc_payload,
    )
    rpc_html = _render_rpc_payload(rpc_payload)
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
    banners: list[str] = []
    if config.ui.show_http_warning:
        banners.append("<p class='banner warning'>Development mode – HTTP only</p>")
    if config.ui.error_taxonomy_banner:
        banners.append("<p class='banner info'>Error taxonomy: user, data, system.</p>")
    chart_html = "".join(item["html"] for item in charts or [])
    watermark_html = _render_watermark_html(watermark)
    styles = (
        ".cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1.25rem;}"
        ".card{border:1px solid #e5e7eb;border-radius:0.75rem;padding:1rem;background:#fff;box-shadow:0 1px 2px rgba(15,23,42,0.08);display:flex;flex-direction:column;gap:0.75rem;}"
        ".card img{width:100%;height:160px;object-fit:cover;border-radius:0.5rem;}"
        ".card h3{margin:0;font-size:1.1rem;color:#111827;}"
        ".card ul{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:0.35rem;color:#374151;font-size:0.9rem;}"
        ".card li{display:flex;gap:0.35rem;align-items:flex-start;}"
        ".card li span{font-weight:600;color:#1f2937;}"
        f"{_PARAMS_STYLES}"
    )
    return _render_html_document(
        styles=styles,
        watermark_html=watermark_html,
        banners_html="".join(banners),
        chart_html=chart_html,
        params_html=params_html,
        summary_html=summary_html,
        content_html=f"<div class='wd-surface'><section class='cards'>{''.join(cards)}</section></div>",
        rpc_html=rpc_html,
    )


_PARAMS_STYLES = (
    ".params-bar{margin-bottom:1.25rem;padding:0.85rem 1rem;border:1px solid #e5e7eb;"
    "border-radius:0.75rem;background:#f9fafb;}"
    ".params-form{display:flex;flex-wrap:wrap;gap:0.75rem;align-items:flex-end;}"
    ".param-field{display:flex;flex-direction:column;gap:0.35rem;min-width:12rem;position:relative;}"
    ".param-field label{font-size:0.85rem;font-weight:600;color:#374151;}"
    ".param-field input,.param-field select,.wd-multi-select-toggle{padding:0.45rem 0.6rem;border:1px solid #d1d5db;"
    "border-radius:0.375rem;font:inherit;background:#fff;min-height:2.25rem;}"
    ".param-field select{min-width:10rem;}"
    ".wd-multi-select{position:relative;width:100%;}"
    ".wd-multi-select-toggle{width:100%;display:flex;align-items:center;justify-content:space-between;cursor:pointer;"
    "color:#111827;gap:0.5rem;text-align:left;}"
    ".wd-multi-select-toggle:hover{border-color:#9ca3af;}"
    ".wd-multi-select-summary{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}"
    ".wd-multi-select-caret{font-size:0.75rem;color:#6b7280;}"
    ".wd-multi-select-panel{position:absolute;z-index:20;top:calc(100% + 0.35rem);left:0;width:100%;min-width:12rem;max-height:16rem;"
    "display:flex;flex-direction:column;border:1px solid #d1d5db;border-radius:0.5rem;background:#fff;box-shadow:0 10px 25px rgba(15,23,42,0.1);}"
    ".wd-multi-select-panel[hidden]{display:none;}"
    ".wd-multi-select-search{padding:0.5rem;border-bottom:1px solid #e5e7eb;}"
    ".wd-multi-select-search input{width:100%;padding:0.4rem 0.55rem;border:1px solid #d1d5db;border-radius:0.375rem;font:inherit;}"
    ".wd-multi-select-hint{margin:0;padding:0.35rem 0.65rem 0;color:#6b7280;font-size:0.75rem;}"
    ".wd-multi-select-options{margin:0;padding:0.25rem 0.5rem 0.5rem;list-style:none;overflow:auto;flex:1;}"
    ".wd-multi-select-option label{display:flex;align-items:center;gap:0.5rem;padding:0.35rem 0.25rem;border-radius:0.35rem;cursor:pointer;}"
    ".wd-multi-select-option label:hover{background:#f3f4f6;}"
    ".wd-multi-select-option input{accent-color:#2563eb;}"
    ".wd-multi-select-actions{padding:0.45rem 0.65rem;border-top:1px solid #e5e7eb;display:flex;justify-content:flex-end;}"
    ".wd-multi-select-clear{border:none;background:none;color:#2563eb;font:inherit;cursor:pointer;padding:0.25rem 0.5rem;border-radius:0.35rem;}"
    ".wd-multi-select-clear:hover{background:rgba(37,99,235,0.08);}"
    ".wd-multi-select-input{display:none;}"
    ".param-help{font-size:0.75rem;color:#6b7280;margin:0;}"
    ".param-actions{display:flex;align-items:center;gap:0.75rem;}"
    ".param-actions button{padding:0.45rem 0.95rem;border-radius:0.375rem;border:1px solid #2563eb;"
    "background:#2563eb;color:#fff;font:inherit;cursor:pointer;}"
    ".param-actions button:hover{background:#1d4ed8;border-color:#1d4ed8;}"
    ".param-actions .reset-link{color:#2563eb;text-decoration:none;font-size:0.9rem;}"
    ".param-actions .reset-link:hover{text-decoration:underline;}"
    ".result-summary{margin:0.5rem 0 1rem 0;color:#374151;font-size:0.9rem;}"
    ".rpc-actions{margin-top:1rem;display:flex;gap:1rem;align-items:center;}"
    ".rpc-actions a{color:#2563eb;text-decoration:none;font-weight:600;}"
    ".rpc-actions a:hover{text-decoration:underline;}"
    ".pagination{margin-top:1rem;}"
    ".pagination a{color:#2563eb;text-decoration:none;font-weight:600;}"
    ".pagination a:hover{text-decoration:underline;}"
    "@media(max-width:720px){.params-form{flex-direction:column;align-items:stretch;}.param-field{width:100%;}"
    ".wd-multi-select-panel{position:fixed;left:1rem;right:1rem;top:auto;bottom:1.5rem;max-height:60vh;}.wd-multi-select{width:100%;}}"
)


def _render_watermark_html(watermark: str | None) -> str:
    if not watermark:
        return ""
    return f"<div class='watermark'>{html.escape(watermark)}</div>"


def _render_html_document(
    *,
    styles: Sequence[str] | str,
    watermark_html: str,
    banners_html: str,
    chart_html: str,
    params_html: str,
    summary_html: str,
    content_html: str,
    rpc_html: str,
) -> str:
    style_parts: list[str] = list(_BASE_LAYOUT_STYLES)
    if styles:
        if isinstance(styles, str):
            style_parts.append(styles)
        else:
            style_parts.extend(styles)
    style_text = "".join(style_parts)

    top_sections: list[str] = []
    if banners_html:
        top_sections.append(f"<div class='wd-banners'>{banners_html}</div>")
    if summary_html:
        top_sections.append(f"<div class='wd-summary'>{summary_html}</div>")

    filters_button = ""
    if params_html:
        filters_id = "wd-filters-area"
        filters_block = (
            f"<div class='wd-filters' data-wd-filters id='{filters_id}'>"
            + params_html
            + "</div>"
        )
        top_sections.append(filters_block)
        filters_button = (
            "<button type='button' class='wd-top-button' data-wd-filters-toggle "
            f"data-hide-label='Hide filters' data-show-label='Show filters' aria-controls='{filters_id}' aria-expanded='true'>Hide filters</button>"
        )

    top_html = ""
    if top_sections:
        top_html = (
            "<header class='wd-top' data-wd-top data-hidden='false' data-collapsed='false'>"
            "<div class='wd-top-inner'>"
            "<div class='wd-top-actions'>"
            "<button type='button' class='wd-top-button' data-wd-top-toggle data-hide-label='Hide header' data-show-label='Show header' aria-expanded='true'>Hide header</button>"
            + filters_button
            + "</div><div class='wd-top-sections'>"
            + "".join(top_sections)
            + "</div></div></header>"
        )

    chart_section = f"<div class='wd-chart-block'>{chart_html}</div>" if chart_html else ""
    html_attrs = " data-has-top='true'" if top_html else ""
    body = (
        "<html"
        + html_attrs
        + "><head><style>"
        + style_text
        + "</style></head><body>"
        + watermark_html
        + "<div class='wd-shell'>"
        + top_html
        + "<main class='wd-main'><div class='wd-main-inner'>"
        + chart_section
        + content_html
        + rpc_html
        + "</div></main></div>"
        + _TOP_BAR_SCRIPT
        + "</body></html>"
    )
    return body


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
    pagination: Mapping[str, object] | None = None,
    route_metadata: Mapping[str, object] | None = None,
    cache_meta: Mapping[str, object] | None = None,
    current_table: pa.Table | None = None,
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
    invariant_settings = _extract_invariant_settings(route_metadata, cache_meta)
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
    if pagination:
        for key in ("limit", "offset"):
            value = pagination.get(key)
            if value in {None, ""}:
                continue
            hidden_inputs.append(
                "<input type='hidden' name='"
                + html.escape(str(key))
                + "' value='"
                + html.escape(_stringify_param_value(value))
                + "'/>"
            )

    fields: list[str] = []
    multi_script_needed = False
    for spec in selected_specs:
        control = str(spec.extra.get("ui_control", "")).lower()
        if control not in {"input", "select"}:
            continue
        label = str(spec.extra.get("ui_label") or spec.name.replace("_", " ").title())
        value = values.get(spec.name, spec.default)
        selected_values = _normalize_selected_values(value)
        value_str = _stringify_param_value(value)
        field_html = ["<div class='param-field'>"]
        label_target = f"param-{spec.name}"
        if control == "select":
            label_target += "-toggle"
        field_html.append(
            "<label for='"
            + html.escape(label_target)
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
                + "' id='"
                + html.escape(f"param-{spec.name}")
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
            raw_options = spec.extra.get("options")
            options = _resolve_select_options(
                spec,
                values,
                raw_options,
                invariant_settings,
                cache_meta,
                current_table,
            )
            placeholder_text = str(spec.extra.get("ui_placeholder") or "All values")
            field_html.append(
                _render_multi_select_control(
                    spec.name,
                    options,
                    selected_values,
                    placeholder_text,
                )
            )
            multi_script_needed = True
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
    if multi_script_needed:
        form_html.append(_MULTI_SELECT_SCRIPT)
    return "".join(form_html)


def _input_attrs_for_spec(spec: ParameterSpec) -> tuple[str, str]:
    if spec.type is ParameterType.INTEGER:
        return "number", ""
    if spec.type is ParameterType.FLOAT:
        return "number", " step='any'"
    if spec.type is ParameterType.BOOLEAN:
        return "text", ""
    return "text", ""


def _render_multi_select_control(
    name: str,
    options: Sequence[tuple[str, str]],
    selected_values: Sequence[str],
    placeholder: str,
) -> str:
    select_id = f"param-{name}"
    toggle_id = f"{select_id}-toggle"
    panel_id = f"{select_id}-panel"
    selected_set = {value for value in selected_values}
    rendered_options = list(options) if options else [("", "")]
    summary_labels = [
        label for value, label in rendered_options if value in selected_set and label
    ]
    summary_text = ", ".join(summary_labels) if summary_labels else placeholder
    parts: list[str] = []
    parts.append("<div class='wd-multi-select' data-wd-multi>")
    parts.append(
        "<button type='button' id='"
        + html.escape(toggle_id)
        + "' class='wd-multi-select-toggle' aria-haspopup='listbox' aria-expanded='false' aria-controls='"
        + html.escape(panel_id)
        + "'>"
        + "<span class='wd-multi-select-summary'>"
        + html.escape(summary_text or placeholder)
        + "</span><span class='wd-multi-select-caret' aria-hidden='true'>▾</span></button>"
    )
    parts.append(
        "<div class='wd-multi-select-panel' id='"
        + html.escape(panel_id)
        + "' role='listbox' aria-multiselectable='true' hidden>"
    )
    parts.append(
        "<div class='wd-multi-select-search'><input type='search' placeholder='Filter options' aria-label='Filter options' autocomplete='off'/></div>"
    )
    parts.append(
        "<p class='wd-multi-select-hint'>Selections stay checked as you filter.</p>"
    )
    parts.append("<ul class='wd-multi-select-options'>")
    for opt_value, opt_label in rendered_options:
        safe_value = html.escape(opt_value)
        safe_label = html.escape(opt_label)
        search_key = html.escape(f"{opt_label} {opt_value}".lower())
        checked_attr = " checked" if opt_value in selected_set else ""
        parts.append(
            "<li class='wd-multi-select-option' data-search='"
            + search_key
            + "'><label><input type='checkbox' value='"
            + safe_value
            + "'"
            + checked_attr
            + "/><span>"
            + safe_label
            + "</span></label></li>"
        )
    parts.append("</ul>")
    parts.append(
        "<div class='wd-multi-select-actions'><button type='button' class='wd-multi-select-clear'>Clear</button></div>"
    )
    parts.append("</div>")
    parts.append(
        "<select id='"
        + html.escape(select_id)
        + "' name='"
        + html.escape(name)
        + "' class='wd-multi-select-input' multiple data-placeholder='"
        + html.escape(placeholder)
        + "'>"
    )
    for opt_value, opt_label in rendered_options:
        selected_attr = " selected" if opt_value in selected_set else ""
        parts.append(
            "<option value='"
            + html.escape(opt_value)
            + "'"
            + selected_attr
            + ">"
            + html.escape(opt_label)
            + "</option>"
        )
    parts.append("</select>")
    parts.append("</div>")
    return "".join(parts)


_MULTI_SELECT_SCRIPT = (
    "<script>(function(){"
    "function init(container){"
    "if(container.dataset.wdMultiInit){return;}"
    "container.dataset.wdMultiInit='1';"
    "var select=container.querySelector('select.wd-multi-select-input');"
    "if(!select){return;}"
    "var toggle=container.querySelector('.wd-multi-select-toggle');"
    "var panel=container.querySelector('.wd-multi-select-panel');"
    "var search=container.querySelector('.wd-multi-select-search input');"
    "var summary=container.querySelector('.wd-multi-select-summary');"
    "var clear=container.querySelector('.wd-multi-select-clear');"
    "var options=Array.from(container.querySelectorAll('.wd-multi-select-option'));"
    "function updateFlags(){options.forEach(function(li){var cb=li.querySelector('input');li.dataset.selected=cb&&cb.checked?'1':'';});}"
    "function updateSummary(){var labels=Array.from(select.selectedOptions).map(function(o){return (o.textContent||'').trim();}).filter(Boolean);var text=labels.length?labels.join(', '):(select.dataset.placeholder||'All values');summary.textContent=text;}"
    "options.forEach(function(li){var cb=li.querySelector('input');if(!cb){return;}cb.addEventListener('change',function(){Array.from(select.options).forEach(function(opt){if(opt.value===cb.value){opt.selected=cb.checked;}});updateFlags();updateSummary();});});"
    "if(clear){clear.addEventListener('click',function(){Array.from(select.options).forEach(function(opt){opt.selected=false;});options.forEach(function(li){var cb=li.querySelector('input');if(cb){cb.checked=false;}});updateFlags();updateSummary();});}"
    "function closePanel(){if(panel){panel.hidden=true;}if(toggle){toggle.setAttribute('aria-expanded','false');}}"
    "if(toggle){toggle.addEventListener('click',function(ev){ev.preventDefault();var expanded=toggle.getAttribute('aria-expanded')==='true';if(expanded){closePanel();}else{toggle.setAttribute('aria-expanded','true');if(panel){panel.hidden=false;}if(search){setTimeout(function(){try{search.focus({preventScroll:true});}catch(_){search.focus();}},10);}}});}"
    "document.addEventListener('click',function(ev){if(!container.contains(ev.target)){closePanel();}});"
    "if(panel){panel.addEventListener('keydown',function(ev){if(ev.key==='Escape'){closePanel();if(toggle){toggle.focus();}}});}"
    "if(search){search.addEventListener('input',function(){var term=search.value.toLowerCase();options.forEach(function(li){var hay=(li.getAttribute('data-search')||'');if(!term){li.style.display='';return;}if(li.dataset.selected==='1'){li.style.display='';return;}li.style.display=hay.indexOf(term)===-1?'none':'';});});}"
    "updateFlags();updateSummary();"
    "}"
    "function boot(){document.querySelectorAll('[data-wd-multi]').forEach(init);}" 
    "if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',boot);}else{boot();}" 
    "})();</script>"
)


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


_UNIQUE_VALUES_SENTINEL = "...unique_values..."


def _resolve_select_options(
    spec: ParameterSpec,
    current_values: Mapping[str, object],
    raw_options: object,
    invariant_settings: Mapping[str, InvariantFilterSetting],
    cache_meta: Mapping[str, object] | None,
    current_table: pa.Table | None,
) -> list[tuple[str, str]]:
    static_prefill: list[tuple[str, str]] = []
    wants_dynamic = False
    if isinstance(raw_options, Sequence) and not isinstance(raw_options, (str, bytes, bytearray)):
        filtered_items: list[Any] = []
        for item in raw_options:
            if isinstance(item, str) and item.strip().lower() == _UNIQUE_VALUES_SENTINEL:
                wants_dynamic = True
                continue
            filtered_items.append(item)
        if wants_dynamic:
            static_prefill = _normalize_options(filtered_items)
    elif isinstance(raw_options, str):
        if raw_options.strip().lower() == _UNIQUE_VALUES_SENTINEL:
            wants_dynamic = True
    elif raw_options is None:
        wants_dynamic = True

    if wants_dynamic:
        dynamic = _unique_invariant_options(
            spec,
            invariant_settings,
            cache_meta,
            current_values,
            current_table,
        )
        if not dynamic:
            dynamic = _unique_options_from_table(
                spec,
                current_table,
                current_values,
            )
        combined = _merge_option_lists(dynamic or [("", "")], static_prefill)
        return combined or [("", "")]

    return _normalize_options(raw_options)


def _merge_option_lists(
    dynamic: list[tuple[str, str]],
    static: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    merged: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value, label in dynamic + static:
        if value in seen:
            continue
        merged.append((value, label))
        seen.add(value)
    return merged


def _unique_options_from_table(
    spec: ParameterSpec,
    table: pa.Table | None,
    current_values: Mapping[str, object],
) -> list[tuple[str, str]]:
    if table is None:
        return []
    column_name = _resolve_option_column_name(spec, table)
    if column_name is None:
        return []
    column = table.column(column_name)
    seen: set[str] = set()
    options: list[tuple[str, str]] = []
    for value in column.to_pylist():
        option_value = _stringify_param_value(value)
        if option_value in seen:
            continue
        label = "" if option_value == "" else str(value)
        options.append((option_value, label))
        seen.add(option_value)
    options.sort(key=lambda item: item[1].lower())
    if "" not in seen:
        options.insert(0, ("", ""))
        seen.add("")
    for current_value in _normalize_selected_values(current_values.get(spec.name)):
        if current_value and current_value not in seen:
            options.append((current_value, current_value))
            seen.add(current_value)
    return options


def _filter_options_by_table_values(
    spec: ParameterSpec,
    options: list[tuple[str, str]],
    table: pa.Table | None,
) -> list[tuple[str, str]]:
    if table is None:
        return options
    column_name = _resolve_option_column_name(spec, table)
    if column_name is None:
        return options
    column = table.column(column_name)
    table_values = {
        _stringify_param_value(value)
        for value in column.to_pylist()
    }
    if not table_values:
        return [item for item in options if item[0] == ""]
    return [item for item in options if item[0] in table_values or item[0] == ""]


def _resolve_option_column_name(
    spec: ParameterSpec,
    table: pa.Table,
) -> str | None:
    extra = spec.extra if isinstance(spec.extra, Mapping) else {}
    candidates: list[str] = []
    for key in ("options_column", "column", "value_column"):
        raw = extra.get(key)
        if isinstance(raw, str) and raw:
            candidates.append(raw)
    if spec.name not in candidates:
        candidates.append(spec.name)
    return next((name for name in candidates if name in table.column_names), None)


def _unique_invariant_options(
    spec: ParameterSpec,
    invariant_settings: Mapping[str, InvariantFilterSetting],
    cache_meta: Mapping[str, object] | None,
    current_values: Mapping[str, object],
    current_table: pa.Table | None,
) -> list[tuple[str, str]]:
    param_name = spec.name
    setting = invariant_settings.get(param_name)
    if setting is None:
        return []
    index = _coerce_invariant_index(cache_meta)
    if not index:
        return []
    param_index = index.get(param_name)
    if not isinstance(param_index, Mapping):
        return []

    allowed_pages, filters_applied = _pages_for_other_invariants(
        param_name,
        invariant_settings,
        index,
        current_values,
    )
    if allowed_pages is not None and len(allowed_pages) == 0:
        return [("", "")]

    options: list[tuple[str, str]] = []
    seen: set[str] = set()
    for token, entry in param_index.items():
        if not isinstance(entry, Mapping):
            continue
        entry_pages = _coerce_page_set(entry.get("pages"))
        if allowed_pages is not None and entry_pages is not None:
            if not entry_pages & allowed_pages:
                continue
        value = _token_to_option_value(token, entry)
        if value in seen:
            continue
        label = _token_to_option_label(token, entry)
        options.append((value, label))
        seen.add(value)
    options = _filter_options_by_table_values(spec, options, current_table)
    options.sort(key=lambda item: item[1].lower())
    if not any(value == "" for value, _ in options):
        options.insert(0, ("", ""))

    existing_values = {value for value, _ in options}
    for current_value in _normalize_selected_values(current_values.get(param_name)):
        if current_value and current_value not in existing_values:
            options.append((current_value, current_value))
            existing_values.add(current_value)

    return options


def _normalize_selected_values(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        return []
    if isinstance(raw, (str, bytes, bytearray)):
        return [_stringify_param_value(raw)]
    if isinstance(raw, Iterable):
        values: list[str] = []
        for item in raw:
            value = _stringify_param_value(item)
            if value not in values:
                values.append(value)
        return values
    return [_stringify_param_value(raw)]


def _coerce_invariant_index(
    cache_meta: Mapping[str, object] | None,
) -> Mapping[str, Mapping[str, Mapping[str, object]]] | None:
    if not isinstance(cache_meta, Mapping):
        return None
    index = cache_meta.get("invariant_index")
    if isinstance(index, Mapping):
        return index  # type: ignore[return-value]
    return None
def _pages_for_other_invariants(
    target_param: str,
    invariant_settings: Mapping[str, InvariantFilterSetting],
    index: Mapping[str, Mapping[str, Mapping[str, object]]],
    current_values: Mapping[str, object],
) -> tuple[set[int] | None, bool]:
    pages: set[int] | None = None
    filters_applied = False
    for param, setting in invariant_settings.items():
        if param == target_param:
            continue
        raw_value = current_values.get(param)
        normalized_raw = normalize_invariant_value(raw_value, setting)
        normalized = [
            value
            for value in normalized_raw
            if not (isinstance(value, str) and value == "")
        ]
        if not normalized:
            continue
        filters_applied = True
        tokens = {
            canonicalize_invariant_value(value, setting)
            for value in normalized
        }
        if not tokens:
            continue
        param_entry = index.get(param)
        if not isinstance(param_entry, Mapping):
            continue
        token_pages: set[int] = set()
        unknown = False
        for token in tokens:
            entry = param_entry.get(token)
            if not isinstance(entry, Mapping):
                continue
            entry_pages = _coerce_page_set(entry.get("pages"))
            if entry_pages is None:
                unknown = True
                continue
            token_pages.update(entry_pages)
        if not token_pages and not unknown:
            return set(), True
        if not token_pages and unknown:
            continue
        if pages is None:
            pages = token_pages
        else:
            pages &= token_pages
        if pages is not None and not pages:
            return set(), True
    return pages, filters_applied


def _coerce_page_set(pages: object) -> set[int] | None:
    if not isinstance(pages, Sequence):
        return None
    result: set[int] = set()
    for page in pages:
        try:
            result.add(int(page))
        except (TypeError, ValueError):
            continue
    return result or None


def _token_to_option_value(token: str, entry: Mapping[str, object]) -> str:
    sample = entry.get("sample")
    sample_text = str(sample) if isinstance(sample, str) else None
    if token == "__null__":
        return ""
    prefix, _, payload = token.partition(":")
    if prefix == "str":
        return sample_text if sample_text is not None else payload
    if prefix in {"bool", "num", "datetime", "bytes"} and payload:
        return payload
    return sample_text if sample_text is not None else token


def _token_to_option_label(token: str, entry: Mapping[str, object]) -> str:
    sample = entry.get("sample")
    if isinstance(sample, str) and sample:
        return sample
    if token == "__null__":
        return "(null)"
    if token.startswith("str:"):
        return "(blank)"
    prefix, _, payload = token.partition(":")
    return payload or token


def _extract_invariant_settings(
    route_metadata: Mapping[str, object] | None,
    cache_meta: Mapping[str, object] | None,
) -> dict[str, InvariantFilterSetting]:
    settings: dict[str, InvariantFilterSetting] = {}
    if isinstance(route_metadata, Mapping):
        cache_block = route_metadata.get("cache")
        if isinstance(cache_block, Mapping):
            raw_filters = cache_block.get("invariant_filters")
            for setting in parse_invariant_filters(raw_filters):
                settings[setting.param] = setting
    if settings:
        return settings
    index = _coerce_invariant_index(cache_meta)
    if not index:
        return settings
    for param in index.keys():
        if param not in settings:
            settings[param] = InvariantFilterSetting(param=param, column=str(param))
    return settings

def _stringify_param_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _render_summary_html(
    row_count: int,
    pagination: Mapping[str, object] | None,
    rpc_payload: Mapping[str, object] | None,
) -> str:
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


def _render_rpc_payload(rpc_payload: Mapping[str, object] | None) -> str:
    if not rpc_payload:
        return ""
    endpoint = rpc_payload.get("endpoint")
    data = {key: value for key, value in rpc_payload.items() if key != "endpoint"}
    if endpoint:
        data["endpoint"] = endpoint
    try:
        payload_json = json.dumps(data, separators=(",", ":"))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        payload_json = "{}"
    link_html = (
        f"<a class='rpc-download' href='{html.escape(str(endpoint))}'>"
        "Download this slice (Arrow)</a>"
        if endpoint
        else ""
    )
    if not link_html and payload_json == "{}":
        return ""
    safe_json = payload_json.replace("</", "<\\/")
    return (
        "<div class='rpc-actions'>"
        + link_html
        + "</div>"
        + "<script type='application/json' id='wd-rpc-config'>"
        + safe_json
        + "</script>"
    )


def build_chartjs_configs(
    table: pa.Table,
    specs: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    configs: list[dict[str, object]] = []
    if not specs:
        return configs

    for index, raw in enumerate(specs):
        if not isinstance(raw, Mapping):
            continue
        chart_type = str(raw.get("type") or "line").strip() or "line"
        chart_id = str(raw.get("id") or f"chart_{index}")
        x_column = str(raw.get("x") or "").strip()

        y_spec = raw.get("y")
        if isinstance(y_spec, Sequence) and not isinstance(y_spec, (str, bytes)):
            y_columns = [str(item) for item in y_spec if str(item)]
        elif isinstance(y_spec, str):
            y_columns = [y_spec]
        else:
            inferred = [name for name in table.column_names if name != x_column]
            y_columns = inferred[:1]

        if not y_columns:
            continue

        labels = _chartjs_labels(table, x_column)
        datasets = _chartjs_datasets(table, y_columns, raw)
        if not datasets:
            continue

        options = {}
        raw_options = raw.get("options")
        if isinstance(raw_options, Mapping):
            options = dict(raw_options)

        title = raw.get("title") or raw.get("label")
        heading = raw.get("heading") or title
        if heading is None:
            heading = chart_id.replace("_", " ").title()

        base_options = {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "legend": {"display": True},
            },
        }
        if title:
            base_options["plugins"]["title"] = {
                "display": True,
                "text": str(title),
            }
        merged_options = _merge_chart_options(base_options, options)

        config = {
            "type": chart_type,
            "data": {
                "labels": labels,
                "datasets": datasets,
            },
            "options": merged_options,
        }
        configs.append({"id": chart_id, "heading": heading, "config": config})

    return configs


def render_chartjs_html(
    charts: Sequence[Mapping[str, object]],
    *,
    config: Config,
    route_id: str,
    route_title: str | None,
    route_metadata: Mapping[str, object] | None,
    postprocess: Mapping[str, object] | None = None,
    default_script_url: str | None = None,
    embed: bool = False,
) -> str:
    meta = _merge_view_metadata(route_metadata, "chart_js", postprocess)
    default_url = default_script_url or DEFAULT_CHARTJS_SOURCE
    cdn_url = str(meta.get("cdn_url") or default_url)
    page_title = str(meta.get("page_title") or route_title or route_id)
    container_class = str(meta.get("container_class") or "wd-chart-grid")
    card_class = str(meta.get("card_class") or "wd-chart-card")
    canvas_height = int(meta.get("canvas_height") or 320)
    empty_message = str(meta.get("empty_message") or "No chart data available.")

    chart_blocks: list[str] = []
    for chart in charts:
        chart_id = str(chart.get("id"))
        heading = chart.get("heading")
        config_payload = chart.get("config")
        if not chart_id or not isinstance(config_payload, Mapping):
            continue
        config_json = _chartjs_config_json(config_payload)
        heading_html = (
            f"<h2>{html.escape(str(heading))}</h2>" if heading else ""
        )
        chart_blocks.append(
            "<section class='"
            + html.escape(card_class)
            + "'>"
            + heading_html
            + "<canvas id='"
            + html.escape(chart_id)
            + "' data-wd-chart='"
            + html.escape(f"{chart_id}-config")
            + "' height='"
            + html.escape(str(canvas_height))
            + "'></canvas>"
            + "<script type='application/json' id='"
            + html.escape(f"{chart_id}-config")
            + "'>"
            + config_json
            + "</script>"
            + "</section>"
        )

    if not chart_blocks:
        chart_blocks.append(
            "<div class='wd-chart-empty'>" + html.escape(empty_message) + "</div>"
        )

    script_tag = (
        "<script src='"
        + html.escape(cdn_url)
        + "' crossorigin='anonymous'></script>"
    )
    boot_script = (
        "<script>(function(){"
        "function init(canvas){"
        "var configId=canvas.getAttribute('data-wd-chart');"
        "if(!configId){return;}"
        "var configEl=document.getElementById(configId);"
        "if(!configEl||canvas.dataset.wdChartLoaded){return;}"
        "canvas.dataset.wdChartLoaded='1';"
        "var cfg=JSON.parse(configEl.textContent||'{}');"
        "var ctx=canvas.getContext('2d');"
        "if(window.Chart){new Chart(ctx,cfg);}"
        "}"
        "function run(){"
        "document.querySelectorAll('canvas[data-wd-chart]').forEach(init);"
        "}"
        "if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',run);}"
        "else{run();}"
        "})();</script>"
    )

    content = (
        "<div class='"
        + html.escape(container_class)
        + "'>"
        + "".join(chart_blocks)
        + "</div>"
    )

    if embed:
        return script_tag + content + boot_script

    banners: list[str] = []
    if config.ui.show_http_warning:
        banners.append("<p class='banner warning'>Development mode – HTTP only</p>")
    if config.ui.error_taxonomy_banner:
        banners.append(
            "<p class='banner info'>Charts suppress internal error details.</p>"
        )

    styles = (
        "body{font-family:system-ui,sans-serif;margin:1.5rem;background:#f9fafb;"
        "color:#111827;}"
        ".wd-chart-grid{display:grid;gap:1.5rem;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));}"
        ".wd-chart-card{background:#fff;padding:1rem;border-radius:0.75rem;box-shadow:0 1px 2px rgba(15,23,42,.08);}"
        ".wd-chart-card h2{margin:0 0 0.75rem;font-size:1rem;font-weight:600;}"
        "canvas{max-width:100%;}"
        ".wd-chart-empty{padding:1rem;color:#6b7280;font-style:italic;}"
        ".banner.warning{color:#b91c1c;}"
        ".banner.info{color:#2563eb;}"
    )

    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>"
        + html.escape(page_title)
        + "</title><style>"
        + styles
        + "</style></head><body>"
        + "".join(banners)
        + script_tag
        + content
        + boot_script
        + "</body></html>"
    )


def _chartjs_labels(table: pa.Table, column: str) -> list[object]:
    if column and column in table.column_names:
        values = table.column(column).to_pylist()
        return [_json_friendly(value) for value in values]
    return list(range(1, table.num_rows + 1))


def _chartjs_datasets(
    table: pa.Table,
    columns: Sequence[str],
    spec: Mapping[str, object],
) -> list[dict[str, object]]:
    datasets: list[dict[str, object]] = []
    if not columns:
        return datasets

    palette = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#6366f1", "#14b8a6"]
    label_overrides = spec.get("dataset_labels")
    color_overrides = spec.get("colors")
    dataset_overrides = spec.get("dataset_options")

    for idx, column in enumerate(columns):
        if column not in table.column_names:
            continue
        values = table.column(column).to_pylist()
        converted = [_coerce_numeric(value) for value in values]
        if not any(item is not None for item in converted):
            continue

        if len(converted) > table.num_rows:
            converted = converted[: table.num_rows]
        elif len(converted) < table.num_rows:
            converted.extend([None] * (table.num_rows - len(converted)))

        if isinstance(label_overrides, Sequence) and not isinstance(
            label_overrides, (str, bytes)
        ) and idx < len(label_overrides):
            label = str(label_overrides[idx])
        else:
            label = spec.get("label") if len(columns) == 1 else column
            label = str(label)

        if isinstance(color_overrides, Sequence) and not isinstance(
            color_overrides, (str, bytes)
        ) and idx < len(color_overrides):
            color = str(color_overrides[idx])
        else:
            color = palette[idx % len(palette)]

        dataset = {
            "label": label,
            "data": converted,
            "borderColor": color,
            "backgroundColor": color,
        }
        if str(spec.get("type") or "line").strip().lower() in {"line", "radar"}:
            dataset["fill"] = False
            dataset["tension"] = 0.25

        if isinstance(dataset_overrides, Mapping):
            dataset.update(dataset_overrides)
        elif isinstance(dataset_overrides, Sequence) and not isinstance(
            dataset_overrides, (str, bytes)
        ) and idx < len(dataset_overrides):
            override = dataset_overrides[idx]
            if isinstance(override, Mapping):
                dataset.update(override)

        datasets.append(dataset)

    return datasets


def _merge_chart_options(
    base: Mapping[str, object],
    overrides: Mapping[str, object] | None,
) -> dict[str, object]:
    merged = dict(base)
    if not overrides:
        return merged
    for key, value in overrides.items():
        if (
            key in merged
            and isinstance(merged[key], Mapping)
            and isinstance(value, Mapping)
        ):
            merged[key] = _merge_chart_options(merged[key], value)
        else:
            merged[key] = value
    return merged


def _chartjs_config_json(config: Mapping[str, object]) -> str:
    try:
        payload = json.dumps(
            config,
            default=_json_friendly,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        payload = "{}"
    return payload.replace("</", "<\\/")


def _coerce_numeric(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dt.datetime):
        return value.timestamp()
    if isinstance(value, dt.date):
        return float(dt.datetime.combine(value, dt.time.min).timestamp())
    try:
        text = str(value)
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


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
    styles = (
        ".wd-feed{display:flex;flex-direction:column;gap:1.5rem;}"
        ".wd-feed section{margin:0;display:flex;flex-direction:column;gap:0.75rem;}"
        ".wd-feed h3{margin:0;font-size:1.05rem;color:#111827;}"
        ".wd-feed article{padding:0.75rem 0;border-bottom:1px solid #e5e7eb;display:flex;flex-direction:column;gap:0.35rem;}"
        ".wd-feed article:last-child{border-bottom:none;}"
        ".wd-feed h4{margin:0;font-size:1rem;color:#111827;}"
        ".wd-feed p{margin:0;color:#374151;font-size:0.9rem;}"
        ".wd-feed time{color:#6b7280;font-size:0.8rem;}"
    )
    content_html = f"<div class='wd-surface wd-feed'>{''.join(sections)}</div>"
    return _render_html_document(
        styles=styles,
        watermark_html="",
        banners_html=taxonomy,
        chart_html="",
        params_html="",
        summary_html="",
        content_html=content_html,
        rpc_html="",
    )


def _json_friendly(value: object) -> object:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


__all__ = [
    "render_cards_html_with_assets",
    "render_feed_html",
    "render_chartjs_html",
    "build_chartjs_configs",
    "render_table_html",
    "table_to_records",
]
