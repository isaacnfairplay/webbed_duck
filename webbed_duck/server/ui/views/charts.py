"""Chart view fragments."""
from __future__ import annotations

import html
from typing import Mapping, Sequence

from ..charts import chart_config_json


def render_chart_grid(
    charts: Sequence[Mapping[str, object]],
    *,
    container_class: str,
    card_class: str,
    canvas_height: int,
    empty_message: str,
) -> str:
    blocks: list[str] = []
    for chart in charts:
        chart_id = str(chart.get("id"))
        config_payload = chart.get("config")
        if not chart_id or not isinstance(config_payload, Mapping):
            continue
        heading = chart.get("heading")
        config_json = chart_config_json(config_payload)
        heading_html = f"<h2>{html.escape(str(heading))}</h2>" if heading else ""
        blocks.append(
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
    if not blocks:
        blocks.append(
            "<div class='wd-chart-empty'>" + html.escape(empty_message) + "</div>"
        )
    return (
        "<div class='"
        + html.escape(container_class)
        + "'>"
        + "".join(blocks)
        + "</div>"
    )


__all__ = ["render_chart_grid"]
