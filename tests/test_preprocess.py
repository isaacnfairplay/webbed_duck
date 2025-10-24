from __future__ import annotations

from pathlib import Path

import pyarrow as pa

from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import RouteDefinition, load_compiled_routes
from webbed_duck.core.local import run_route
from webbed_duck.server.preprocess import run_preprocessors


def _make_route_definition() -> RouteDefinition:
    return RouteDefinition(
        id="example",
        path="/example",
        methods=["GET"],
        raw_sql="SELECT ?",
        prepared_sql="SELECT ?",
        param_order=["name"],
        params=(),
        metadata={},
    )


def test_run_preprocessors_supports_varied_signatures() -> None:
    route = _make_route_definition()
    steps = [
        {
            "callable": "tests.fake_preprocessors:add_prefix",
            "prefix": "pre-",
            "options": {"prefix": "pre-", "note": "memo"},
        },
        {"callable": "tests.fake_preprocessors:add_suffix", "suffix": "-post"},
        {"callable": "tests.fake_preprocessors:return_none"},
    ]
    result = run_preprocessors(steps, {"name": "value"}, route=route, request=None)
    assert result["name"] == "pre-value-post"
    # note merged from options payload
    assert result["note"] == "memo"


def test_run_preprocessors_integrates_with_local_runner(tmp_path: Path) -> None:
    route_text = (
        "+++\n"
        "id = \"pre_route\"\n"
        "path = \"/pre\"\n"
        "[params.name]\n"
        "type = \"str\"\n"
        "required = true\n"
        "+++\n\n"
        "<!-- @preprocess {\"callable\": \"tests.fake_preprocessors:uppercase_value\", \"field\": \"name\"} -->\n"
        "```sql\nSELECT {{name}} AS result\n```\n"
    )
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    src_dir.mkdir()
    (src_dir / "pre.sql.md").write_text(route_text, encoding="utf-8")
    compile_routes(src_dir, build_dir)
    routes = load_compiled_routes(build_dir)

    table = run_route("pre_route", params={"name": "duck"}, routes=routes, build_dir=build_dir)
    assert isinstance(table, pa.Table)
    assert table.column("result")[0].as_py() == "DUCK"
