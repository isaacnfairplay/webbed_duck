"""HTML fragments for card views."""
from __future__ import annotations

import html
from typing import Mapping, Sequence


def render_cards(cards: Sequence[Mapping[str, object]]) -> str:
    card_html: list[str] = []
    for card in cards:
        title = html.escape(str(card.get("title", "")))
        image = card.get("image")
        meta_items = card.get("meta")
        image_html = (
            f"<img src='{html.escape(str(image))}' alt='{title}'/>"
            if image
            else ""
        )
        meta_html = ""
        if isinstance(meta_items, Sequence):
            meta_parts = []
            for entry in meta_items:
                if not isinstance(entry, Sequence) or len(entry) != 2:
                    continue
                label, value = entry
                meta_parts.append(
                    "<li><span>"
                    + html.escape(str(label))
                    + "</span>: "
                    + html.escape(str(value))
                    + "</li>"
                )
            meta_html = "<ul>" + "".join(meta_parts) + "</ul>"
        card_html.append(
            "<article class='card'>"
            + image_html
            + f"<h3>{title}</h3>"
            + meta_html
            + "</article>"
        )
    return "<div class='wd-surface'><section class='cards'>" + "".join(card_html) + "</section></div>"


__all__ = ["render_cards"]
