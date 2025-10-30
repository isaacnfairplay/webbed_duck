from __future__ import annotations

from webbed_duck.server.ui.layout import UIAssets, render_layout


def test_render_layout_includes_theme_toggle() -> None:
    html = render_layout(
        page_title='Demo',
        banners_html='',
        summary_html='',
        filters_html='',
        main_blocks_html=["<div class='wd-surface'>Body</div>"],
        watermark_html='',
        assets=UIAssets(widgets=(), styles=(), scripts=()),
    )

    assert "data-wd-theme-toggle" in html
    assert "wd-top-button--ghost" in html
    assert "data-has-top='true'" in html
