from __future__ import annotations

import pyarrow as pa

from webbed_duck.config import load_config
from webbed_duck.core.routes import ParameterSpec, ParameterType
from webbed_duck.server.postprocess import render_cards_html_with_assets, render_table_html


def test_render_table_html_renders_controls_and_rpc() -> None:
    config = load_config(None)
    config.ui.show_http_warning = True
    config.ui.error_taxonomy_banner = True

    table = pa.table({"greeting": ["Hello"], "count": [1]})
    params = [
        ParameterSpec(
            name="name",
            type=ParameterType.STRING,
            extra={
                "ui_control": "input",
                "ui_label": "Name",
                "ui_placeholder": "Friend",
                "ui_help": "Enter a name and press Apply",
            },
        )
    ]

    html = render_table_html(
        table,
        {"html_t": {"show_params": ["name"]}},
        config,
        charts=[{"html": "<div>chart</div>"}],
        params=params,
        param_values={"name": "Mallard", "format": "html_t", "other": "persist"},
        format_hint="html_t",
        pagination={"limit": 10, "offset": 0},
        rpc_payload={
            "endpoint": "/rpc/table",
            "total_rows": 25,
            "limit": 10,
            "offset": 0,
            "next_href": "/rpc/table?offset=10",
        },
    )

    assert "Development mode – HTTP only" in html
    assert "Errors follow the webbed_duck taxonomy" in html
    assert "<label for='param-name'>Name</label>" in html
    assert "placeholder='Friend'" in html
    assert "Enter a name and press Apply" in html
    assert "name='other' value='persist'" in html
    assert "name='format' value='html_t'" in html
    assert "Showing 1–1 of 25 rows" in html
    assert "Download this slice (Arrow)" in html
    assert "<script type='application/json' id='wd-rpc-config'>" in html
    assert "Mallard" in html


def test_render_cards_html_includes_assets_and_select_options() -> None:
    config = load_config(None)
    config.ui.show_http_warning = True
    config.ui.error_taxonomy_banner = True

    table = pa.table({"title": ["Widget"], "image": ["card.png"], "status": ["OK"]})
    params = [
        ParameterSpec(
            name="status",
            type=ParameterType.STRING,
            extra={
                "ui_control": "select",
                "options": [
                    {"value": "OK", "label": "On Track"},
                    {"value": "NG", "label": "Needs Attention"},
                ],
            },
        )
    ]

    html = render_cards_html_with_assets(
        table,
        {"html_c": {"show_params": ["status"], "image_col": "image"}},
        config,
        charts=[{"html": "<div>chart</div>"}],
        assets={"base_path": "media", "image_getter": "static_fallback"},
        route_id="demo/route",
        params=params,
        param_values={"status": "OK"},
        pagination={"limit": 1, "offset": 0},
        rpc_payload={"endpoint": "/rpc/cards", "total_rows": 1},
    )

    assert "<section class='cards'>" in html
    assert "<img src='/static/media/card.png'" in html
    assert "<select id='param-status'" in html
    assert "<option value='OK' selected>On Track</option>" in html
    assert "Development mode – HTTP only" in html
    assert "Error taxonomy: user, data, system." in html
    assert "<div>chart</div>" in html
