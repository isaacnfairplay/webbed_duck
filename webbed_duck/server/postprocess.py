"""Server-side HTML renderers for webbed_duck."""
from __future__ import annotations

from typing import Mapping, Sequence

import html
import pyarrow as pa

from .. import __version__ as PACKAGE_VERSION
from ..config import Config
from ..core.routes import ParameterSpec
from ..plugins.assets import resolve_image
from .ui.charts import build_chartjs_configs as _build_chart_configs
from .ui.layout import render_layout, resolve_assets
from .ui.pagination import render_summary
from .ui.rpc import render_rpc_payload
from .ui.utils import table_to_records
from .ui.views.cards import render_cards
from .ui.views.charts import render_chart_grid
from .ui.views.feed import render_feed
from .ui.views.table import render_table
from .ui.widgets.params import render_params_form


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
    view_meta = _merge_view_metadata(route_metadata, "html_t", postprocess)
    params_html = render_params_form(
        view_meta,
        params,
        param_values,
        format_hint=format_hint,
        pagination=pagination,
        route_metadata=route_metadata,
        cache_meta=cache_meta,
        current_table=table,
    )
    summary_html = render_summary(len(records), pagination, rpc_payload)
    rpc_html = render_rpc_payload(rpc_payload)

    chart_block = ""
    if charts:
        chart_block = (
            "<div class='wd-chart-block'>"
            + "".join(item.get("html", "") for item in charts)
            + "</div>"
        )

    banners_html = _build_banners(config)
    watermark_html = _render_watermark_html(watermark)

    main_blocks = [block for block in [chart_block, render_table(headers, records), rpc_html] if block]
    assets = resolve_assets(
        route_metadata,
        default_widgets=["header", "params", "multi_select"],
        default_styles=["layout", "table", "params", "multi_select"],
        default_scripts=["header", "multi_select", "params", "table_header"],
    )

    return render_layout(
        page_title=view_meta.get("page_title") if isinstance(view_meta, Mapping) else None,
        banners_html=banners_html,
        summary_html=summary_html,
        filters_html=params_html,
        main_blocks_html=main_blocks,
        watermark_html=watermark_html,
        assets=assets,
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
    records = table_to_records(table)
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

    getter_name = str(assets.get("image_getter")) if assets and assets.get("image_getter") else None
    base_path = str(assets.get("base_path")) if assets and assets.get("base_path") else None

    cards_payload: list[dict[str, object]] = []
    for record in records:
        title = record.get(title_col, "")
        meta_items = [(col, record.get(col, "")) for col in meta_cols]
        image_html = None
        if image_col and record.get(image_col):
            image_value = str(record[image_col])
            if base_path and not image_value.startswith(("/", "http://", "https://")):
                image_value = f"{base_path.rstrip('/')}/{image_value}"
            resolved = resolve_image(image_value, route_id, getter_name=getter_name)
            image_html = resolved
        cards_payload.append({"title": title, "image": image_html, "meta": meta_items})

    params_html = render_params_form(
        cards_meta,
        params,
        param_values,
        format_hint=format_hint,
        pagination=pagination,
        route_metadata=route_metadata,
        cache_meta=cache_meta,
        current_table=table,
    )
    summary_html = render_summary(len(records), pagination, rpc_payload)
    rpc_html = render_rpc_payload(rpc_payload)

    chart_block = ""
    if charts:
        chart_block = (
            "<div class='wd-chart-block'>"
            + "".join(item.get("html", "") for item in charts)
            + "</div>"
        )

    banners_html = _build_banners(config)
    watermark_html = _render_watermark_html(watermark)

    main_blocks = [block for block in [chart_block, render_cards(cards_payload), rpc_html] if block]
    resolved_assets = resolve_assets(
        route_metadata,
        default_widgets=["header", "params", "multi_select"],
        default_styles=["layout", "cards", "params", "multi_select"],
        default_scripts=["header", "multi_select", "params"],
    )

    return render_layout(
        page_title=str(cards_meta.get("page_title") or metadata.get("title") or route_id),
        banners_html=banners_html,
        summary_html=summary_html,
        filters_html=params_html,
        main_blocks_html=main_blocks,
        watermark_html=watermark_html,
        assets=resolved_assets,
    )


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
    summary_field = str(summary_col) if isinstance(summary_col, str) else None
    feed_html = render_feed(
        records,
        timestamp_field=ts_col,
        title_field=title_col,
        summary_field=summary_field,
    )

    banners_html = ""
    if config.ui.error_taxonomy_banner:
        banners_html = "<aside class='banner info'>Feeds suppress sensitive system errors.</aside>"

    assets = resolve_assets(
        route_metadata,
        default_widgets=["header"],
        default_styles=["layout", "feed"],
        default_scripts=["header"],
    )

    return render_layout(
        page_title=str(metadata.get("title") or "Activity feed"),
        banners_html=banners_html,
        summary_html="",
        filters_html="",
        main_blocks_html=[feed_html],
        watermark_html="",
        assets=assets,
    )


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
    default_url = default_script_url or (config.ui.chartjs_source or "")
    cdn_url = str(meta.get("cdn_url") or default_url)
    page_title = str(meta.get("page_title") or route_title or route_id)
    container_class = str(meta.get("container_class") or "wd-chart-grid")
    card_class = str(meta.get("card_class") or "wd-chart-card")
    canvas_height = int(meta.get("canvas_height") or 320)
    empty_message = str(meta.get("empty_message") or "No chart data available.")

    chart_grid = render_chart_grid(
        charts,
        container_class=container_class,
        card_class=card_class,
        canvas_height=canvas_height,
        empty_message=empty_message,
    )

    assets = resolve_assets(
        route_metadata,
        default_widgets=["header", "charts"],
        default_styles=["layout", "charts"],
        default_scripts=["header", "chart_boot"],
        extra_scripts=["chart_boot"],
    )

    if embed:
        script_tag = (
            "<script src='"
            + html.escape(cdn_url)
            + "' crossorigin='anonymous'></script>"
        )
        boot_tag = (
            "<script type='module' src='/assets/wd/chart_boot.js?v="
            + html.escape(PACKAGE_VERSION)
            + "'></script>"
        )
        return script_tag + chart_grid + boot_tag

    banners_html = _build_banners(config)
    watermark_html = ""

    return render_layout(
        page_title=page_title,
        banners_html=banners_html,
        summary_html="",
        filters_html="",
        main_blocks_html=[chart_grid],
        watermark_html=watermark_html,
        assets=assets,
        body_data={"wd-chart-src": cdn_url} if cdn_url else None,
    )


def build_chartjs_configs(
    table: pa.Table,
    specs: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    return _build_chart_configs(table, specs)


def _build_banners(config: Config) -> str:
    banners: list[str] = []
    if config.ui.show_http_warning:
        banners.append("<p class='banner warning'>Development mode – HTTP only</p>")
    if config.ui.error_taxonomy_banner:
        banners.append("<p class='banner info'>Errors follow the webbed_duck taxonomy (see docs).</p>")
    return "".join(banners)


def _render_watermark_html(watermark: str | None) -> str:
    if not watermark:
        return ""
    return f"<div class='watermark'>{html.escape(watermark)}</div>"


def _merge_view_metadata(
    route_metadata: Mapping[str, object] | None,
    key: str,
    postprocess: Mapping[str, object] | None,
) -> Mapping[str, object]:
    metadata = route_metadata or {}
    merged: dict[str, object] = {}
    base = metadata.get(key)
    if isinstance(base, Mapping):
        merged.update(base)
    if isinstance(postprocess, Mapping):
        merged.update(postprocess)
    return merged


__all__ = [
    "render_cards_html_with_assets",
    "render_feed_html",
    "render_chartjs_html",
    "build_chartjs_configs",
    "render_table_html",
    "table_to_records",
]
