from __future__ import annotations

import pyarrow as pa

from webbed_duck.config import load_config
from webbed_duck.core.routes import ParameterSpec, ParameterType
from webbed_duck.server.postprocess import (
    build_chartjs_configs,
    render_cards_html_with_assets,
    render_chartjs_html,
    render_table_html,
)
from webbed_duck.server.ui.layout import render_layout, resolve_assets
from webbed_duck.server.ui.views.table import render_table
from webbed_duck.server.ui.widgets.params import render_params_form
from webbed_duck.static.chartjs import CHARTJS_FILENAME, CHARTJS_VERSION


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
    assert "/assets/wd/layout.css" in html
    assert "/assets/wd/table.css" in html
    assert "/assets/wd/header.js" in html
    assert "/assets/wd/multi_select.js" in html
    assert "/assets/wd/table_header.js" in html
    assert "data-wd-widget='params'" in html
    assert "<label for='param-name'>Name</label>" in html
    assert "placeholder='Friend'" in html
    assert "Enter a name and press Apply" in html
    assert "name='other' value='persist'" in html
    assert "name='format' value='html_t'" in html
    assert "Showing 1–1 of 25 rows" in html
    assert "Download this slice (Arrow)" in html
    assert "<script type='application/json' id='wd-rpc-config'>" in html
    assert "Mallard" in html
    assert "<div class='wd-table-mini' data-wd-table-mini hidden>" in html
    assert "<span class='wd-table-mini-label'>greeting</span>" in html
    assert "<span class='wd-table-mini-label'>count</span>" in html


def test_render_table_html_uses_invariant_unique_values() -> None:
    config = load_config(None)
    table = pa.table({"Division": ["Engineering", "Finance", "Manufacturing"]})
    params = [
        ParameterSpec(
            name="division",
            type=ParameterType.STRING,
            extra={
                "ui_control": "select",
                "options": "...unique_values...",
            },
        )
    ]
    cache_meta = {
        "invariant_index": {
            "division": {
                "str:Engineering": {"pages": [0], "rows": 1, "sample": "Engineering"},
                "str:Finance": {"pages": [0], "rows": 1, "sample": "Finance"},
            }
        }
    }

    html = render_table_html(
        table,
        {"html_t": {"show_params": ["division"]}},
        config,
        charts=[],
        params=params,
        param_values={"division": ""},
        format_hint="html_t",
        cache_meta=cache_meta,
    )

    assert "<div class='wd-multi-select' data-wd-widget='multi'>" in html
    assert "<select id='param-division' name='division' class='wd-multi-select-input' multiple" in html
    assert "data-search='engineering engineering'" in html
    assert "data-search='finance finance'" in html
    assert "wd-multi-select-clear'>Clear</button>" in html
    assert "<option value='Manufacturing'" not in html


def test_render_table_html_select_without_options_uses_invariant_index() -> None:
    config = load_config(None)
    table = pa.table({"division": ["Engineering", "Finance", "Manufacturing"]})
    params = [
        ParameterSpec(
            name="division",
            type=ParameterType.STRING,
            extra={
                "ui_control": "select",
            },
        )
    ]
    cache_meta = {
        "invariant_index": {
            "division": {
                "str:Engineering": {"pages": [0], "rows": 1, "sample": "Engineering"},
                "str:Finance": {"pages": [0], "rows": 1, "sample": "Finance"},
            }
        }
    }

    html = render_table_html(
        table,
        {"html_t": {"show_params": ["division"]}},
        config,
        charts=[],
        params=params,
        param_values={"division": ""},
        format_hint="html_t",
        cache_meta=cache_meta,
    )

    assert "<div class='wd-multi-select' data-wd-widget='multi'>" in html
    assert "<select id='param-division' name='division' class='wd-multi-select-input' multiple" in html
    assert "<option value=''" in html
    assert "data-search='engineering engineering'" in html
    assert "data-search='finance finance'" in html
    assert "Selections stay checked as you filter." in html
    assert "<option value='Manufacturing'" not in html


def test_render_table_html_invariant_options_follow_filtered_rows() -> None:
    config = load_config(None)
    table = pa.table({"division": ["Finance"], "region": ["EMEA"]})
    params = [
        ParameterSpec(
            name="division",
            type=ParameterType.STRING,
            extra={
                "ui_control": "select",
                "options": "...unique_values...",
            },
        )
    ]
    cache_meta = {
        "invariant_index": {
            "division": {
                "str:Engineering": {"pages": [0], "rows": 10, "sample": "Engineering"},
                "str:Finance": {"pages": [0], "rows": 5, "sample": "Finance"},
            }
        }
    }

    html = render_table_html(
        table,
        {"html_t": {"show_params": ["division"]}},
        config,
        charts=[],
        params=params,
        param_values={"division": "", "region": "EMEA"},
        format_hint="html_t",
        cache_meta=cache_meta,
    )

    assert "<div class='wd-multi-select' data-wd-widget='multi'>" in html
    assert "<select id='param-division' name='division' class='wd-multi-select-input' multiple" in html
    assert "data-search='finance finance'" in html
    assert "<option value='Engineering'" not in html


def test_render_table_html_invariant_options_keep_selected_value() -> None:
    config = load_config(None)
    table = pa.table({"division": ["Finance"]})
    params = [
        ParameterSpec(
            name="division",
            type=ParameterType.STRING,
            extra={
                "ui_control": "select",
                "options": "...unique_values...",
            },
        )
    ]
    cache_meta = {
        "invariant_index": {
            "division": {
                "str:Engineering": {"pages": [0], "rows": 10, "sample": "Engineering"},
                "str:Finance": {"pages": [0], "rows": 5, "sample": "Finance"},
            }
        }
    }

    html = render_table_html(
        table,
        {"html_t": {"show_params": ["division"]}},
        config,
        charts=[],
        params=params,
        param_values={"division": "Engineering"},
        format_hint="html_t",
        cache_meta=cache_meta,
    )

    assert "<select id='param-division' name='division' class='wd-multi-select-input' multiple" in html
    assert "<option value='Engineering' selected>Engineering</option>" in html
    assert "<option value='Finance'>Finance</option>" in html


def test_render_table_html_select_without_options_defaults_to_table_unique_values() -> None:
    config = load_config(None)
    table = pa.table({"division": ["Engineering", "Finance", "Engineering"]})
    params = [
        ParameterSpec(
            name="division",
            type=ParameterType.STRING,
            extra={
                "ui_control": "select",
            },
        )
    ]

    html = render_table_html(
        table,
        {"html_t": {"show_params": ["division"]}},
        config,
        charts=[],
        params=params,
        param_values={"division": ""},
        format_hint="html_t",
        cache_meta=None,
    )

    assert "<select id='param-division' name='division' class='wd-multi-select-input' multiple" in html
    assert "<option value='' selected>" in html
    assert "<option value='Engineering'>Engineering</option>" in html
    assert "<option value='Finance'>Finance</option>" in html


def test_render_table_html_select_marks_multiple_selected_values() -> None:
    config = load_config(None)
    table = pa.table({"division": ["Engineering", "Finance", "Manufacturing"]})
    params = [
        ParameterSpec(
            name="division",
            type=ParameterType.STRING,
            extra={
                "ui_control": "select",
            },
        )
    ]

    html = render_table_html(
        table,
        {"html_t": {"show_params": ["division"]}},
        config,
        charts=[],
        params=params,
        param_values={"division": ["Engineering", "Finance"]},
        format_hint="html_t",
        cache_meta=None,
    )

    assert "<select id='param-division' name='division' class='wd-multi-select-input' multiple" in html
    assert "<option value='Engineering' selected>Engineering</option>" in html
    assert "<option value='Finance' selected>Finance</option>" in html
    assert "<option value='Manufacturing'" in html


def test_render_table_html_falls_back_to_table_unique_values() -> None:
    config = load_config(None)
    table = pa.table({"division": ["Engineering", "Finance", "Engineering"]})
    params = [
        ParameterSpec(
            name="division",
            type=ParameterType.STRING,
            extra={
                "ui_control": "select",
                "options": ["...unique_values...", {"value": "Other", "label": "Other"}],
            },
        )
    ]

    html = render_table_html(
        table,
        {"html_t": {"show_params": ["division"]}},
        config,
        charts=[],
        params=params,
        param_values={"division": ""},
        format_hint="html_t",
        cache_meta=None,
    )

    assert "<select id='param-division' name='division' class='wd-multi-select-input' multiple" in html
    assert "<option value='' selected>" in html
    assert "<option value='Engineering'>Engineering</option>" in html
    assert "<option value='Finance'>Finance</option>" in html
    assert "<option value='Other'>Other</option>" in html


def test_render_table_html_invariant_options_keep_multiple_selected_values() -> None:
    config = load_config(None)
    table = pa.table({"division": ["Finance"]})
    params = [
        ParameterSpec(
            name="division",
            type=ParameterType.STRING,
            extra={
                "ui_control": "select",
                "options": "...unique_values...",
            },
        )
    ]
    cache_meta = {
        "invariant_index": {
            "division": {
                "str:Engineering": {"pages": [0], "rows": 10, "sample": "Engineering"},
                "str:Finance": {"pages": [0], "rows": 5, "sample": "Finance"},
            }
        }
    }

    html = render_table_html(
        table,
        {"html_t": {"show_params": ["division"]}},
        config,
        charts=[],
        params=params,
        param_values={"division": ["Engineering", "Finance"]},
        format_hint="html_t",
        cache_meta=cache_meta,
    )

    assert "<select id='param-division' name='division' class='wd-multi-select-input' multiple" in html
    assert "<option value='Finance' selected>Finance</option>" in html
    assert "<option value='Engineering' selected>Engineering</option>" in html


def test_render_table_html_numeric_invariant_filters_other_options() -> None:
    config = load_config(None)
    table = pa.table({"region": ["EMEA", "APAC"], "year": [2023, 2024]})
    params = [
        ParameterSpec(
            name="year",
            type=ParameterType.INTEGER,
            extra={
                "ui_control": "select",
                "options": "...unique_values...",
            },
        ),
        ParameterSpec(
            name="region",
            type=ParameterType.STRING,
            extra={
                "ui_control": "select",
                "options": "...unique_values...",
            },
        ),
    ]
    cache_meta = {
        "invariant_index": {
            "year": {
                "num:2023": {"pages": [0], "rows": 5, "sample": "2023"},
                "num:2024": {"pages": [1], "rows": 4, "sample": "2024"},
            },
            "region": {
                "str:EMEA": {"pages": [0], "rows": 5, "sample": "EMEA"},
                "str:APAC": {"pages": [1], "rows": 4, "sample": "APAC"},
            },
        }
    }

    html = render_table_html(
        table,
        {"html_t": {"show_params": ["year", "region"]}},
        config,
        charts=[],
        params=params,
        param_values={"year": 2023, "region": ""},
        format_hint="html_t",
        cache_meta=cache_meta,
    )

    assert "<select id='param-year' name='year' class='wd-multi-select-input' multiple" in html
    assert "<option value='2023' selected>2023</option>" in html
    assert "<option value='2024'" in html
    assert "data-search='emea emea'" in html
    assert "data-search='apac apac'" not in html


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
    assert "<select id='param-status' name='status' class='wd-multi-select-input' multiple" in html
    assert "wd-multi-select-clear'>Clear</button>" in html
    assert "<option value='OK' selected>On Track</option>" in html
    assert "/assets/wd/cards.css" in html
    assert "/assets/wd/multi_select.js" in html
    assert "Development mode – HTTP only" in html
    assert "Errors follow the webbed_duck taxonomy" in html
    assert "<div>chart</div>" in html


def test_chartjs_build_and_render_embed_modes() -> None:
    config = load_config(None)
    config.ui.show_http_warning = True
    config.ui.error_taxonomy_banner = True

    table = pa.table({"day": ["Mon", "Tue"], "value": [1, 3]})
    specs = [
        {
            "id": "trend",
            "type": "line",
            "x": "day",
            "y": "value",
            "title": "Values",
        }
    ]

    charts = build_chartjs_configs(table, specs)
    assert charts and charts[0]["config"]["type"] == "line"
    assert charts[0]["config"]["data"]["labels"] == ["Mon", "Tue"]

    full_html = render_chartjs_html(
        charts,
        config=config,
        route_id="demo",
        route_title="Demo",
        route_metadata={"chart_js": {"canvas_height": 240}},
        default_script_url=f"/vendor/{CHARTJS_FILENAME}?v={CHARTJS_VERSION}",
        embed=False,
    )
    assert "<!doctype html>" in full_html
    assert f"/vendor/{CHARTJS_FILENAME}?v={CHARTJS_VERSION}" in full_html
    assert "/assets/wd/charts.css" in full_html
    assert "/assets/wd/chart_boot.js" in full_html
    assert "data-wd-chart='trend-config'" in full_html
    assert "Development mode – HTTP only" in full_html
    assert "Errors follow the webbed_duck taxonomy" in full_html

    embed_html = render_chartjs_html(
        charts,
        config=config,
        route_id="demo",
        route_title="Demo",
        route_metadata={},
        default_script_url=f"/vendor/{CHARTJS_FILENAME}?v={CHARTJS_VERSION}",
        embed=True,
    )
    assert "<!doctype html>" not in embed_html
    assert embed_html.count("<canvas") == 1
    assert "/assets/wd/chart_boot.js" in embed_html


def test_chartjs_uses_ui_config_source() -> None:
    config = load_config(None)
    config.ui.chartjs_source = "https://cdn.example.com/chart.js"

    table = pa.table({"day": ["Mon"], "value": [1]})
    specs = [
        {
            "id": "trend",
            "type": "bar",
            "x": "day",
            "y": "value",
            "title": "Values",
        }
    ]

    charts = build_chartjs_configs(table, specs)

    html = render_chartjs_html(
        charts,
        config=config,
        route_id="demo",
        route_title="Demo",
        route_metadata={},
        default_script_url=None,
        embed=False,
    )

    assert "data-wd-chart-src='https://cdn.example.com/chart.js'" in html

def test_params_form_renders_hidden_inputs_and_multi_select() -> None:
    table = pa.table({"region": ["EMEA", "APAC"]})
    params = [
        ParameterSpec(
            name="search",
            type=ParameterType.STRING,
            extra={"ui_control": "input", "ui_label": "Search"},
        ),
        ParameterSpec(
            name="region",
            type=ParameterType.STRING,
            extra={"ui_control": "select"},
        ),
    ]

    html = render_params_form(
        {"show_params": ["search", "region"]},
        params,
        {"search": "engine", "format": "html_t"},
        format_hint="html_t",
        pagination={"limit": 25},
        current_table=table,
    )

    assert "class='params-form'" in html
    assert "name='format' value='html_t'" in html
    assert "name='limit' value='25'" in html
    assert "<div class='wd-multi-select' data-wd-widget='multi'>" in html
    assert "<option value='EMEA'>EMEA</option>" in html
    assert "<option value='APAC'>APAC</option>" in html


def test_table_view_renders_header_and_rows() -> None:
    html = render_table(["col_a", "col_b"], [{"col_a": "x", "col_b": "y"}])
    assert "<th>col_a</th>" in html
    assert "<td>x</td>" in html
    assert "<td>y</td>" in html


def test_layout_emits_requested_assets_once() -> None:
    assets = resolve_assets(
        {"ui": {"styles": ["table"], "scripts": ["header"]}},
        default_styles=["layout", "table"],
        default_scripts=["header"],
        extra_scripts=["chart_boot"],
    )

    html = render_layout(
        page_title="Demo",
        banners_html="",
        summary_html="",
        filters_html="",
        main_blocks_html=["<p>Body</p>"],
        watermark_html="",
        assets=assets,
    )

    assert html.count("/assets/wd/layout.css") == 1
    assert html.count("/assets/wd/table.css") == 1
    assert html.count("src='/assets/wd/header.js") == 1
    assert html.count("src='/assets/wd/chart_boot.js") == 1
