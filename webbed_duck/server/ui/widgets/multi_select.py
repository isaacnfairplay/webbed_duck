"""Server-rendered multi-select widget."""
from __future__ import annotations

from typing import Sequence


def render_multi_select(
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
    parts.append("<div class='wd-multi-select' data-wd-widget='multi'>")
    parts.append(
        "<button type='button' id='"
        + _escape(toggle_id)
        + "' class='wd-multi-select-toggle' aria-haspopup='listbox' aria-expanded='false' aria-controls='"
        + _escape(panel_id)
        + "'>"
        + "<span class='wd-multi-select-summary'>"
        + _escape(summary_text or placeholder)
        + "</span><span class='wd-multi-select-caret' aria-hidden='true'>▾</span></button>"
    )
    parts.append(
        "<div class='wd-multi-select-panel' id='"
        + _escape(panel_id)
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
        safe_value = _escape(opt_value)
        safe_label = _escape(opt_label)
        search_key = _escape(f"{opt_label} {opt_value}".lower())
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
        "<div class='wd-multi-select-actions'>"
        "<button type='button' class='wd-multi-select-select-all'>Select all matches</button>"
        "<button type='button' class='wd-multi-select-clear'>Clear</button>"
        "</div>"
    )
    parts.append("</div>")
    parts.append(
        "<select id='"
        + _escape(select_id)
        + "' name='"
        + _escape(name)
        + "' class='wd-multi-select-input' multiple data-placeholder='"
        + _escape(placeholder)
        + "'>"
    )
    for opt_value, opt_label in rendered_options:
        selected_attr = " selected" if opt_value in selected_set else ""
        parts.append(
            "<option value='"
            + _escape(opt_value)
            + "'"
            + selected_attr
            + ">"
            + _escape(opt_label)
            + "</option>"
        )
    parts.append("</select>")
    parts.append("</div>")
    return "".join(parts)


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


__all__ = ["render_multi_select"]
