"""Server-side HTML layout assembly for webbed_duck."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Mapping, Sequence

from ... import __version__ as PACKAGE_VERSION


_ASSET_BASE = "/assets/wd"
_STYLE_PATHS: Mapping[str, str] = {
    "layout": "layout.css",
    "params": "params.css",
    "multi_select": "multi_select.css",
    "table": "table.css",
    "cards": "cards.css",
    "feed": "feed.css",
    "charts": "charts.css",
}
_SCRIPT_PATHS: Mapping[str, str] = {
    "header": "header.js",
    "multi_select": "multi_select.js",
    "params": "params_form.js",
    "table_header": "table_header.js",
    "chart_boot": "chart_boot.js",
}

_WIDGET_ORDER: tuple[str, ...] = ("header", "params", "multi_select")
_STYLE_ORDER: tuple[str, ...] = ("layout", "params", "multi_select", "table", "cards", "feed", "charts")
_SCRIPT_ORDER: tuple[str, ...] = ("header", "params", "multi_select", "table_header", "chart_boot")


@dataclass(frozen=True)
class UIAssets:
    """Resolved UI asset requirements for a rendered page."""

    widgets: tuple[str, ...]
    styles: tuple[str, ...]
    scripts: tuple[str, ...]

    def __bool__(self) -> bool:  # pragma: no cover - convenience only
        return bool(self.widgets or self.styles or self.scripts)


def resolve_assets(
    route_metadata: Mapping[str, object] | None,
    *,
    default_widgets: Iterable[str] = (),
    default_styles: Iterable[str] = (),
    default_scripts: Iterable[str] = (),
    extra_styles: Iterable[str] = (),
    extra_scripts: Iterable[str] = (),
) -> UIAssets:
    """Merge default UI asset requests with per-route metadata.

    The ``[ui]`` table in a compiled route metadata dictionary may define
    ``widgets``, ``styles``, and ``scripts`` arrays. This helper combines those
    declarations with defaults supplied by the renderer while preserving the
    caller's requested order.
    """

    ui_section = route_metadata.get("ui") if isinstance(route_metadata, Mapping) else None
    widgets = _ordered_union(
        _iter_metadata(ui_section.get("widgets")) if isinstance(ui_section, Mapping) else (),
        default_widgets,
        canonical_order=_WIDGET_ORDER,
    )
    styles = _ordered_union(
        _iter_metadata(ui_section.get("styles")) if isinstance(ui_section, Mapping) else (),
        default_styles,
        extra_styles,
        canonical_order=_STYLE_ORDER,
    )
    scripts = _ordered_union(
        _iter_metadata(ui_section.get("scripts")) if isinstance(ui_section, Mapping) else (),
        default_scripts,
        extra_scripts,
        canonical_order=_SCRIPT_ORDER,
    )
    return UIAssets(widgets, styles, scripts)


def render_layout(
    *,
    page_title: str | None,
    banners_html: str,
    summary_html: str,
    filters_html: str,
    main_blocks_html: Sequence[str],
    watermark_html: str,
    assets: UIAssets,
    body_data: Mapping[str, str] | None = None,
    chart_source: str | None = None,
) -> str:
    """Assemble the final HTML document.

    ``banners_html``, ``summary_html`` and ``filters_html`` should contain the
    rendered fragments for the sticky header. ``main_blocks_html`` is rendered
    in order inside the main container.
    """

    top_sections: list[str] = []
    if banners_html:
        top_sections.append(f"<div class='wd-banners'>{banners_html}</div>")
    if summary_html:
        top_sections.append(f"<div class='wd-summary'>{summary_html}</div>")

    filters_id = "wd-filters"
    filters_button = ""
    if filters_html:
        top_sections.append(
            "<div class='wd-filters' data-wd-filters id='"
            + filters_id
            + "'>"
            + filters_html
            + "</div>"
        )
        filters_button = (
            "<button type='button' class='wd-top-button' data-wd-filters-toggle "
            "data-hide-label='Hide filters' data-show-label='Show filters' "
            f"aria-controls='{filters_id}' aria-expanded='true'>Hide filters</button>"
        )

    top_html = ""
    theme_button = (
        "<button type='button' class='wd-top-button wd-top-button--ghost' data-wd-theme-toggle "
        "data-dark-label='Use dark theme' data-light-label='Use light theme' "
        "data-system-label='System theme ({theme})' "
        "data-hint='Click to toggle theme. Alt-click to follow your system preference.' "
        "aria-pressed='mixed'>System theme (light)</button>"
    )

    top_sections_html = "".join(top_sections)
    if top_sections_html or filters_button or theme_button:
        sections_block = (
            "<div class='wd-top-sections'>" + top_sections_html + "</div>"
            if top_sections_html
            else ""
        )
        top_html = (
            "<header class='wd-top' data-wd-top data-hidden='false' data-collapsed='false'>"
            "<div class='wd-top-inner'>"
            "<div class='wd-top-actions'>"
            + theme_button
            + "<button type='button' class='wd-top-button' data-wd-top-toggle "
            "data-hide-label='Hide header' data-show-label='Show header' "
            "aria-expanded='true'>Hide header</button>"
            + filters_button
            + "</div>"
            + sections_block
            + "</div></header>"
        )

    html_attrs = []
    if top_html:
        html_attrs.append("data-has-top='true'")
    html_attr_text = (" " + " ".join(html_attrs)) if html_attrs else ""

    body_attrs: dict[str, str] = {}
    if body_data:
        for key, value in body_data.items():
            body_attrs[f"data-{key}"] = value
    if assets.widgets:
        body_attrs["data-wd-widgets"] = " ".join(sorted(set(assets.widgets)))
    if chart_source:
        body_attrs["data-wd-chart-src"] = chart_source
    body_attr_text = "".join(f" {k}='{_escape_attr(v)}'" for k, v in body_attrs.items())

    head_parts = ["<meta charset='utf-8'>"]
    if page_title:
        head_parts.append("<title>" + _escape_text(page_title) + "</title>")
    head_parts.extend(_style_links(assets.styles))
    head_parts.extend(_script_preloads(assets.scripts))

    document = ["<!doctype html>"]
    document.append("<html" + html_attr_text + "><head>")
    document.extend(head_parts)
    document.append("</head><body" + body_attr_text + ">")
    if watermark_html:
        document.append(watermark_html)
    document.append("<div class='wd-shell'>")
    document.append(top_html)
    document.append("<main class='wd-main'><div class='wd-main-inner'>")
    document.extend(main_blocks_html)
    document.append("</div></main></div>")
    document.extend(_script_tags(assets.scripts))
    document.append("</body></html>")
    return "".join(document)


def _style_links(style_names: Iterable[str]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for name in style_names:
        if name in seen:
            continue
        seen.add(name)
        path = _STYLE_PATHS.get(name)
        if not path:
            continue
        tags.append(
            "<link rel='stylesheet' href='"
            + f"{_ASSET_BASE}/{path}?v={PACKAGE_VERSION}"
            + "'>"
        )
    return tags


def _script_preloads(script_names: Iterable[str]) -> list[str]:
    tags: list[str] = []
    for name in script_names:
        if name not in _SCRIPT_PATHS:
            continue
        path = _SCRIPT_PATHS[name]
        tags.append(
            "<link rel='modulepreload' href='"
            + f"{_ASSET_BASE}/{path}?v={PACKAGE_VERSION}"
            + "'>"
        )
    return tags


def _script_tags(script_names: Iterable[str]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for name in script_names:
        if name in seen:
            continue
        seen.add(name)
        path = _SCRIPT_PATHS.get(name)
        if not path:
            continue
        tags.append(
            "<script type='module' src='"
            + f"{_ASSET_BASE}/{path}?v={PACKAGE_VERSION}"
            + "'></script>"
        )
    return tags


def _iter_metadata(raw: object) -> Iterator[str]:
    if isinstance(raw, str):
        for part in raw.split(","):
            value = part.strip()
            if value:
                yield value
    elif isinstance(raw, Iterable) and not isinstance(raw, (str, bytes)):
        for item in raw:
            if not item:
                continue
            yield str(item)


def _ordered_union(
    metadata: Iterable[str],
    *sources: Iterable[str],
    canonical_order: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Merge metadata and default asset requests while preserving anchors.

    ``metadata`` is assumed to contain the per-route declarations. When
    ``canonical_order`` is supplied the resulting tuple keeps canonical items in
    their base order and only moves custom entries ahead of a canonical anchor
    when they appear immediately before that anchor in ``metadata``.
    """

    def _normalize(items: Iterable[str]) -> Iterator[str]:
        for raw in items:
            if not raw:
                continue
            yield str(raw)

    metadata_order: list[str] = []
    metadata_seen: set[str] = set()
    for item in _normalize(metadata):
        if item in metadata_seen:
            continue
        metadata_seen.add(item)
        metadata_order.append(item)

    seen_all: set[str] = set()
    all_items: list[str] = []
    for item in metadata_order:
        if item in seen_all:
            continue
        seen_all.add(item)
        all_items.append(item)
    for source in sources:
        for item in _normalize(source):
            if item in seen_all:
                continue
            seen_all.add(item)
            all_items.append(item)

    if not canonical_order:
        return tuple(all_items)

    canonical_set = set(canonical_order)
    canonical_items = [name for name in canonical_order if name in seen_all]

    before_map: dict[str, list[str]] = {}
    after_map: dict[str, list[str]] = {}
    trailing_custom: list[str] = []
    used_custom: set[str] = set()
    segment: list[str] = []
    last_canonical: str | None = None
    for item in metadata_order:
        if item in canonical_set:
            if segment:
                target = before_map if last_canonical is None else after_map
                key = item if last_canonical is None else last_canonical
                target.setdefault(key, []).extend(segment)
                used_custom.update(segment)
                segment = []
            last_canonical = item
        else:
            if item not in used_custom:
                segment.append(item)

    if segment:
        if last_canonical is None:
            trailing_custom = segment[:]
        else:
            after_map.setdefault(last_canonical, []).extend(segment)
        used_custom.update(segment)

    ordered: list[str] = []
    for name in canonical_items:
        ordered.extend(before_map.get(name, ()))
        ordered.append(name)
        ordered.extend(after_map.get(name, ()))

    if trailing_custom:
        for item in trailing_custom:
            if item not in ordered:
                ordered.append(item)

    for item in all_items:
        if item in canonical_set or item in used_custom:
            continue
        if item not in ordered:
            ordered.append(item)

    return tuple(ordered)


def _escape_text(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _escape_attr(value: str) -> str:
    return (
        _escape_text(value)
        .replace("'", "&#39;")
        .replace('"', "&quot;")
    )


__all__ = ["UIAssets", "resolve_assets", "render_layout"]
