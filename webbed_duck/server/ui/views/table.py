"""HTML fragments for the table view."""
from __future__ import annotations

import html
from typing import Mapping, Sequence


def render_table(headers: Sequence[str], records: Sequence[Mapping[str, object]]) -> str:
    header_html = "".join(f"<th>{html.escape(col)}</th>" for col in headers)
    rows: list[str] = []
    for row in records:
        cells = [
            f"<td>{html.escape(str(row.get(col, '')))}</td>"
            for col in headers
        ]
        rows.append("<tr>" + "".join(cells) + "</tr>")
    rows_html = "".join(rows)
    return (
        "<div class='wd-surface wd-surface--flush wd-table'>"
        "<div class='wd-table-scroller'>"
        "<table>"
        "<thead><tr>"
        + header_html
        + "</tr></thead><tbody>"
        + rows_html
        + "</tbody></table></div></div>"
    )


__all__ = ["render_table"]
