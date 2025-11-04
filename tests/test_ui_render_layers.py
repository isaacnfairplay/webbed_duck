import datetime as dt
import json

import pyarrow as pa
import pytest

from webbed_duck import __version__
from webbed_duck.core.routes import ParameterSpec, ParameterType
from webbed_duck.server.cache import InvariantFilterSetting
from webbed_duck.server.ui.charts import build_chartjs_configs, chart_config_json
from webbed_duck.server.ui.invariants import (
    coerce_invariant_index,
    coerce_page_set,
    extract_invariant_settings,
    pages_for_other_invariants,
    token_to_option_label,
    token_to_option_value,
)
from webbed_duck.server.ui.layout import UIAssets, render_layout, resolve_assets
from webbed_duck.server.ui.pagination import render_summary
from webbed_duck.server.ui.rpc import render_rpc_payload
from webbed_duck.server.ui.utils import json_friendly, table_to_records
from webbed_duck.server.ui.views.cards import render_cards
from webbed_duck.server.ui.views.charts import render_chart_grid
from webbed_duck.server.ui.views.feed import render_feed
from webbed_duck.server.ui.views.table import render_table
from webbed_duck.server.ui.widgets.multi_select import render_multi_select
from webbed_duck.server.ui.widgets.params import render_params_form


@pytest.fixture()
def sample_table() -> pa.Table:
    return pa.table(
        {
            "date": [
                dt.date(2024, 1, 1),
                dt.date(2024, 1, 2),
                dt.date(2024, 1, 3),
            ],
            "sales": [1.5, 2.25, 3.75],
            "units": [10, 12, 14],
            "division": ["Ops", "Finance", "Ops"],
        }
    )


def test_resolve_assets_deduplicates_and_orders() -> None:
    metadata = {
        "ui": {
            "widgets": ["params", "multi_select", "params"],
            "styles": ["table", "layout", "charts"],
            "scripts": ["header", "chart_boot"],
        }
    }

    assets = resolve_assets(
        metadata,
        default_widgets=["params"],
        default_styles=["layout"],
        default_scripts=["header"],
        extra_styles=["table", "charts"],
        extra_scripts=["multi_select", "header"],
    )

    assert assets.widgets == ("params", "multi_select")
    assert assets.styles == ("layout", "table", "charts")
    assert assets.scripts == ("header", "multi_select", "chart_boot")


def test_resolve_assets_accepts_csv_strings() -> None:
    metadata = {
        "ui": {
            "widgets": "params",
            "styles": "layout, table , charts",
            "scripts": "header, chart_boot",
        }
    }

    assets = resolve_assets(
        metadata,
        default_styles=["layout"],
        extra_scripts=["multi_select"],
    )

    assert assets.widgets == ("params",)
    assert assets.styles == ("layout", "table", "charts")
    assert assets.scripts == ("header", "multi_select", "chart_boot")


def test_resolve_assets_defaults_precede_custom_when_unanchored() -> None:
    metadata = {"ui": {"styles": ["theme"]}}

    assets = resolve_assets(
        metadata,
        default_styles=["layout", "table"],
    )

    assert assets.styles == ("layout", "table", "theme")


def test_resolve_assets_can_anchor_custom_before_default() -> None:
    metadata = {"ui": {"styles": ["theme", "layout"]}}

    assets = resolve_assets(
        metadata,
        default_styles=["layout", "table"],
    )

    assert assets.styles == ("theme", "layout", "table")


def test_resolve_assets_preserves_custom_order() -> None:
    metadata = {
        "ui": {
            "styles": ["layout", "custom", "cards"],
            "scripts": ["custom_a", "header", "custom_b"],
        }
    }

    assets = resolve_assets(
        metadata,
        default_styles=["layout"],
        default_scripts=["header"],
        extra_styles=["charts"],
        extra_scripts=["chart_boot"],
    )

    assert assets.styles == ("layout", "custom", "cards", "charts")
    assert assets.scripts == ("custom_a", "header", "custom_b", "chart_boot")


def test_render_layout_includes_assets_and_top_sections() -> None:
    assets = UIAssets(
        widgets=("header", "params"),
        styles=("layout", "table"),
        scripts=("multi_select", "header"),
    )

    html = render_layout(
        page_title="Test Page",
        banners_html="<p>Banner</p>",
        summary_html="<p>Summary</p>",
        filters_html="<form>Filters</form>",
        main_blocks_html=["<section>Block A</section>", "<section>Block B</section>"],
        watermark_html="<div id='watermark'></div>",
        assets=assets,
        body_data={"wd-test": "value"},
        chart_source="https://charts.example/cdn.js",
    )

    assert html.startswith("<!doctype html>")
    assert "<html data-has-top='true'>" in html
    assert "<title>Test Page</title>" in html
    assert f"/assets/wd/layout.css?v={__version__}" in html
    assert f"<link rel='modulepreload' href='/assets/wd/multi_select.js?v={__version__}'" in html
    assert f"<script type='module' src='/assets/wd/header.js?v={__version__}'></script>" in html
    assert "data-wd-progress" in html
    assert "data-wd-widgets='header params'" in html
    assert "data-wd-chart-src='https://charts.example/cdn.js'" in html
    assert "data-wd-wd-test='value'" not in html
    assert "data-wd-test='value'" in html
    assert "<header class='wd-top'" in html
    assert "aria-controls='wd-filters'" in html
    assert "<main class='wd-main'" in html
    assert html.endswith("</body></html>")


def test_render_layout_skips_unknown_assets() -> None:
    assets = UIAssets(
        widgets=(),
        styles=("layout", "unknown"),
        scripts=("header", "does-not-exist"),
    )

    html = render_layout(
        page_title="Assets",
        banners_html="",
        summary_html="",
        filters_html="",
        main_blocks_html=["<section>Body</section>"],
        watermark_html="",
        assets=assets,
        body_data=None,
        chart_source=None,
    )

    assert f"/assets/wd/layout.css?v={__version__}" in html
    assert "unknown.css" not in html
    assert f"<script type='module' src='/assets/wd/header.js?v={__version__}'></script>" in html
    assert "does-not-exist" not in html


def test_render_table_outputs_rows_in_order() -> None:
    html = render_table(
        ["name", "count"],
        [
            {"name": "Mallard", "count": 3},
            {"name": "Teal", "count": 5},
        ],
    )

    assert "<thead><tr><th>name</th><th>count</th></tr></thead>" in html
    assert "<td>Mallard</td>" in html
    assert "<td>5</td>" in html
    assert html.count("<tr>") == 3


def test_render_cards_renders_meta_pairs() -> None:
    html = render_cards(
        [
            {
                "title": "Alpha",
                "image": "/img/alpha.png",
                "meta": [("Owner", "Duck"), ("Status", "Green")],
            }
        ]
    )

    assert "<section class='cards'>" in html
    assert "<img src='/img/alpha.png' alt='Alpha'/>" in html
    assert "<span>Owner</span>: Duck" in html
    assert "<h3>Alpha</h3>" in html


def test_render_feed_groups_by_recency() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    records = [
        {
            "timestamp": now.isoformat(),
            "title": "Today item",
            "summary": "Current",
        },
        {
            "timestamp": (now - dt.timedelta(days=1)).isoformat(),
            "title": "Yesterday item",
            "summary": "Previous",
        },
        {
            "timestamp": (now - dt.timedelta(days=5)).isoformat(),
            "title": "Old item",
            "summary": "Historic",
        },
    ]

    html = render_feed(records, timestamp_field="timestamp", title_field="title", summary_field="summary")

    assert "<h3>Today</h3>" in html
    assert "<h3>Yesterday</h3>" in html
    assert "<h3>Earlier</h3>" in html
    assert html.count("<article>") == 3


def test_render_chart_grid_outputs_canvas_and_config(sample_table: pa.Table) -> None:
    configs = build_chartjs_configs(
        sample_table,
        [
            {
                "id": "sales_trend",
                "type": "bar",
                "x": "date",
                "y": ["sales", "units"],
                "title": "Sales",
                "heading": "Sales trend",
                "options": {"scales": {"y": {"beginAtZero": True}}},
                "dataset_labels": ["Revenue", "Units"],
                "colors": ["#111111", "#222222"],
                "dataset_options": [{"borderWidth": 4}, {"borderWidth": 2}],
            }
        ],
    )

    assert len(configs) == 1
    chart = configs[0]
    assert chart["id"] == "sales_trend"
    assert chart["heading"] == "Sales trend"
    data = chart["config"]["data"]
    assert data["labels"] == [value.isoformat() for value in sample_table.column("date").to_pylist()]
    assert len(data["datasets"]) == 2
    assert data["datasets"][0]["label"] == "Revenue"
    assert data["datasets"][0]["data"][0] == pytest.approx(1.5)
    assert chart["config"]["options"]["plugins"]["title"]["text"] == "Sales"

    grid_html = render_chart_grid(
        configs,
        container_class="wd-chart-grid",
        card_class="wd-chart-card",
        canvas_height=240,
        empty_message="No charts",
    )

    assert "<div class='wd-chart-grid'>" in grid_html
    assert "<canvas id='sales_trend'" in grid_html
    assert "data-wd-chart='sales_trend-config'" in grid_html
    assert "<script type='application/json' id='sales_trend-config'" in grid_html

    empty_html = render_chart_grid(
        [],
        container_class="wd-chart-grid",
        card_class="wd-chart-card",
        canvas_height=120,
        empty_message="Nothing to show",
    )
    assert "Nothing to show" in empty_html


def test_build_chart_configs_convert_temporal_and_boolean_series() -> None:
    table = pa.table(
        {
            "recorded_at": [
                dt.datetime(2024, 4, 1, 8, 30, tzinfo=dt.timezone.utc),
                dt.datetime(2024, 4, 2, 9, 0, tzinfo=dt.timezone.utc),
            ],
            "active": [True, False],
        }
    )

    configs = build_chartjs_configs(
        table,
        [
            {
                "id": "status",
                "type": "line",
                "x": "recorded_at",
                "y": ["active", "recorded_at"],
            }
        ],
    )

    assert len(configs) == 1
    datasets = configs[0]["config"]["data"]["datasets"]
    assert datasets[0]["data"] == [1.0, 0.0]
    expected_ts = [value.timestamp() for value in table.column("recorded_at").to_pylist()]
    assert datasets[1]["data"] == pytest.approx(expected_ts)


def test_chart_config_json_escapes_closing_tags() -> None:
    payload = {"data": "</script>"}
    encoded = chart_config_json(payload)
    assert "</script>" not in encoded
    assert r"<\/script>" in encoded


def test_render_multi_select_builds_summary_and_options() -> None:
    html = render_multi_select(
        "division",
        [("ops", "Ops"), ("finance", "Finance")],
        ["finance"],
        "Choose divisions",
    )

    assert "data-wd-widget='multi'" in html
    assert "aria-haspopup='listbox'" in html
    assert "Finance" in html
    assert "<span class='wd-multi-select-summary'>Finance</span>" in html
    assert "data-search='ops ops'" in html
    assert "<option value='finance' selected>Finance</option>" in html


def test_render_params_form_renders_inputs_and_hidden_fields(sample_table: pa.Table) -> None:
    params = [
        ParameterSpec(
            name="name",
            type=ParameterType.STRING,
            extra={"ui_control": "input", "ui_label": "Name", "ui_placeholder": "Friend"},
        ),
        ParameterSpec(
            name="division",
            type=ParameterType.STRING,
            extra={
                "ui_control": "select",
                "ui_label": "Division",
                "ui_placeholder": "All divisions",
                "options": "...unique_values...",
                "ui_help": "Pick a division",
            },
        ),
    ]
    cache_meta = {
        "invariant_index": {
            "division": {
                "str:Finance": {"pages": [0], "rows": 10, "sample": "Finance"},
                "str:Ops": {"pages": [0], "rows": 8, "sample": "Ops"},
            }
        }
    }

    html = render_params_form(
        {"show_params": ["name", "division"]},
        params,
        {"name": "Waddles", "division": ["Finance"], "format": "html_t", "other": "persist"},
        format_hint="html_c",
        pagination={"limit": 25, "offset": 50},
        route_metadata=None,
        cache_meta=cache_meta,
        current_table=sample_table,
    )

    assert "<form method='get' action='?' class='params-form' data-wd-widget='params'>" in html
    assert "placeholder='Friend'" in html
    assert "value='Waddles'" in html
    assert "name='format' value='html_t'" in html
    assert "name='other' value='persist'" in html
    assert "name='limit' value='25'" in html
    assert "name='offset' value='50'" in html
    assert "Pick a division" in html
    assert "<option value='Finance' selected>Finance</option>" in html
    assert "<option value='Ops'>Ops</option>" in html


def test_render_params_form_includes_invariant_specs_when_missing(sample_table: pa.Table) -> None:
    cache_meta = {
        "invariant_index": {
            "region": {
                "str:EMEA": {"pages": [0, 1], "rows": 2, "sample": "EMEA"},
            }
        }
    }
    route_metadata = {
        "cache": {
            "invariant_filters": {
                "region": {"column": "region", "type": "str", "ui_label": "Region"}
            }
        }
    }

    html = render_params_form(
        {"show_params": ["region"]},
        [],
        {"region": "EMEA"},
        pagination=None,
        route_metadata=route_metadata,
        cache_meta=cache_meta,
        current_table=pa.table({"region": ["EMEA", "AMER"]}),
    )

    assert "param-region-toggle" in html
    assert "<option value=''" in html
    assert "<option value='EMEA' selected>EMEA</option>" in html


def test_extract_invariant_settings_prefers_metadata() -> None:
    route_metadata = {
        "cache": {
            "invariant_filters": {
                "division": {
                    "column": "division",
                    "separator": ",",
                    "case_insensitive": True,
                    "type": "str",
                }
            }
        }
    }
    cache_meta = {
        "invariant_index": {
            "division": {
                "str:Ops": {"pages": [0], "rows": 2, "sample": "Ops"}
            }
        }
    }

    settings = extract_invariant_settings(route_metadata, cache_meta)
    assert set(settings.keys()) == {"division"}
    setting = settings["division"]
    assert setting.column == "division"
    assert setting.separator == ","
    assert setting.case_insensitive is True


def test_pages_for_other_invariants_intersects_page_sets() -> None:
    invariant_settings = {
        "division": InvariantFilterSetting(param="division", column="division"),
        "region": InvariantFilterSetting(param="region", column="region"),
    }
    index = {
        "region": {
            "str:EMEA": {"pages": [0, 1]},
            "str:AMER": {"pages": [2]},
        }
    }
    pages, applied = pages_for_other_invariants(
        "division",
        invariant_settings,
        index,
        {"region": "EMEA"},
    )

    assert applied is True
    assert pages == {0, 1}


def test_pages_for_other_invariants_returns_empty_for_unknown() -> None:
    invariant_settings = {
        "division": InvariantFilterSetting(param="division", column="division"),
        "region": InvariantFilterSetting(param="region", column="region"),
    }
    index = {
        "region": {
            "str:EMEA": {"pages": [0, 1]},
        }
    }
    pages, applied = pages_for_other_invariants(
        "division",
        invariant_settings,
        index,
        {"region": "APAC"},
    )

    assert applied is True
    assert pages == set()


def test_coerce_invariant_index_rejects_non_mapping() -> None:
    assert coerce_invariant_index(None) is None
    assert coerce_invariant_index({"other": 123}) is None
    index = {"invariant_index": {"division": {}}}
    assert coerce_invariant_index(index) == index["invariant_index"]


def test_coerce_page_set_filters_invalid_entries() -> None:
    assert coerce_page_set("not-sequence") is None
    assert coerce_page_set(["a", 2, 2]) == {2}


def test_token_conversion_helpers() -> None:
    entry = {"sample": "Finance"}
    assert token_to_option_value("str:Finance", entry) == "Finance"
    assert token_to_option_label("str:Finance", entry) == "Finance"
    null_entry = {"sample": None}
    assert token_to_option_value("__null__", null_entry) == "__null__"
    assert token_to_option_label("__null__", null_entry) == "(null)"


def test_render_summary_includes_pagination_link() -> None:
    summary = render_summary(
        10,
        {"offset": 10, "limit": 10},
        {"total_rows": 42, "offset": 10, "limit": 10, "next_href": "/next"},
    )

    assert "Showing 11–20 of 42 rows" in summary
    assert "href='/next'" in summary

    blank = render_summary(5, None, {"total_rows": ""})
    assert blank == ""


def test_render_rpc_payload_outputs_link_and_script() -> None:
    payload = {
        "endpoint": "/rpc/data",
        "total_rows": 5,
        "limit": 10,
    }
    html = render_rpc_payload(payload)
    assert "href='/rpc/data'" in html
    match = json.loads(
        html.split("<script type='application/json' id='wd-rpc-config'>", 1)[1].split("</script>")[0]
    )
    assert match["endpoint"] == "/rpc/data"
    assert match["total_rows"] == 5

    assert render_rpc_payload({}) == ""


def test_table_to_records_serializes_temporals(sample_table: pa.Table) -> None:
    records = table_to_records(sample_table)
    assert records[0]["date"] == sample_table.column("date").to_pylist()[0].isoformat()
    assert records[0]["sales"] == 1.5
    assert len(records) == sample_table.num_rows


def test_table_to_records_serializes_time_values() -> None:
    table = pa.table(
        {
            "event_time": pa.array(
                [dt.time(8, 15, 0), dt.time(12, 30, 45, 123456)],
                type=pa.time64("us"),
            )
        }
    )

    records = table_to_records(table)

    assert records[0]["event_time"] == "08:15:00"
    assert records[1]["event_time"] == "12:30:45.123456"


def test_json_friendly_handles_datetime() -> None:
    value = dt.datetime(2024, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
    assert json_friendly(value) == value.isoformat()
    assert json_friendly(123) == 123
