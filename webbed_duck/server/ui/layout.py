"""Server-side HTML layout assembly for webbed_duck."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

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
    "chart_boot": "chart_boot.js",
}


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
    declarations with defaults supplied by the renderer.
    """

    widgets: set[str] = {item for item in default_widgets if item}
    styles: set[str] = {item for item in default_styles if item}
    scripts: set[str] = {item for item in default_scripts if item}

    ui_section = route_metadata.get("ui") if isinstance(route_metadata, Mapping) else None
    if isinstance(ui_section, Mapping):
        _apply_metadata_list(ui_section.get("widgets"), widgets)
        _apply_metadata_list(ui_section.get("styles"), styles)
        _apply_metadata_list(ui_section.get("scripts"), scripts)

    _apply_metadata_list(extra_styles, styles)
    _apply_metadata_list(extra_scripts, scripts)

    ordered_widgets = tuple(sorted(widgets))
    ordered_styles = tuple(_preserve_requested_order(styles))
    ordered_scripts = tuple(_preserve_requested_order(scripts))
    return UIAssets(ordered_widgets, ordered_styles, ordered_scripts)


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
    if top_sections:
        top_html = (
            "<header class='wd-top' data-wd-top data-hidden='false' data-collapsed='false'>"
            "<div class='wd-top-inner'>"
            "<div class='wd-top-actions'>"
            "<button type='button' class='wd-top-button' data-wd-top-toggle "
            "data-hide-label='Hide header' data-show-label='Show header' "
            "aria-expanded='true'>Hide header</button>"
            + filters_button
            + "</div><div class='wd-top-sections'>"
            + "".join(top_sections)
            + "</div></div></header>"
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


def _apply_metadata_list(raw: object, target: set[str]) -> None:
    if isinstance(raw, str):
        for part in raw.split(","):
            value = part.strip()
            if value:
                target.add(value)
    elif isinstance(raw, Iterable) and not isinstance(raw, (str, bytes)):
        for item in raw:
            if not item:
                continue
            target.add(str(item))


def _preserve_requested_order(values: set[str]) -> list[str]:
    ordered = []
    for key in ("layout", "params", "multi_select", "table", "cards", "feed", "charts"):
        if key in values:
            ordered.append(key)
            values.remove(key)
    ordered.extend(sorted(values))
    return ordered


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
