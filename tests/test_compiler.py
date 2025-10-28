from __future__ import annotations

from pathlib import Path

import pytest

from webbed_duck.core.compiler import RouteCompilationError, compile_route_file, compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app
from webbed_duck.config import load_config

from tests.conftest import write_sidecar_route


def _write_pair(tmp_path: Path, stem: str, toml: str, sql: str, doc: str | None = None) -> None:
    toml_path = tmp_path / f"{stem}.toml"
    toml_path.write_text(toml, encoding="utf-8")
    sql_path = tmp_path / f"{stem}.sql"
    sql_path.write_text(sql, encoding="utf-8")
    if doc:
        (tmp_path / f"{stem}.md").write_text(doc, encoding="utf-8")

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - allow import error during type checking
    TestClient = None  # type: ignore


def write_route(tmp_path: Path, content: str) -> Path:
    write_sidecar_route(tmp_path, "sample", content)
    return tmp_path / "sample.toml"


def test_compile_collects_directives(tmp_path: Path) -> None:
    route_text = (
        "+++\n"
        "id = \"sample\"\n"
        "path = \"/sample\"\n"
        "[cache]\n"
        "order_by = [\"value\"]\n"
        "+++\n\n"
        "<!-- @cache ttl=30 scope=route -->\n"
        "<!-- @notes important -->\n"
        "```sql\nSELECT 1 AS value\n```\n"
    )
    definition = compile_route_file(write_route(tmp_path, route_text))
    assert len(definition.directives) == 2
    assert definition.directives[0].name == "cache"
    assert definition.directives[0].args["ttl"] == "30"
    assert definition.directives[0].args["scope"] == "route"
    assert definition.directives[1].value == "important"

    build_dir = tmp_path / "build"
    compile_routes(tmp_path, build_dir)
    loaded = load_compiled_routes(build_dir)
    assert loaded[0].directives[0].name == "cache"


def test_cache_requires_order_by(tmp_path: Path) -> None:
    route_text = (
        "+++\n"
        "id = \"cache_missing_order\"\n"
        "path = \"/cache_missing_order\"\n"
        "[cache]\n"
        "rows_per_page = 5\n"
        "+++\n\n"
        "```sql\nSELECT 1 AS value\n```\n"
    )
    with pytest.raises(RouteCompilationError):
        compile_route_file(write_route(tmp_path, route_text))


def test_compile_warns_on_unexpected_frontmatter(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    route_text = (
        "+++\n"
        "id = \"sample\"\n"
        "path = \"/sample\"\n"
        "surplus = 10\n"
        "+++\n\n"
        "```sql\nSELECT 1 AS value\n```\n"
    )
    compile_route_file(write_route(tmp_path, route_text))
    captured = capsys.readouterr()
    assert "unexpected frontmatter key(s) surplus" in captured.err
    assert "sample.toml" in captured.err


def test_compile_route(tmp_path: Path) -> None:
    route_text = (
        "+++\n"
        "id = \"sample\"\n"
        "path = \"/sample\"\n"
        "[params.name]\n"
        "type = \"str\"\n"
        "required = true\n"
        "+++\n\n"
        "```sql\nSELECT {{name}} as value\n```\n"
    )
    route_path = write_route(tmp_path, route_text)
    definition = compile_route_file(route_path)
    assert definition.param_order == ["name"]
    assert definition.prepared_sql == "SELECT ? as value"

    build_dir = tmp_path / "build"
    compiled = compile_routes(tmp_path, build_dir)
    assert compiled[0].id == "sample"

    loaded = load_compiled_routes(build_dir)
    assert loaded[0].id == "sample"


def test_compile_from_toml_sql_pair(tmp_path: Path) -> None:
    _write_pair(
        tmp_path,
        "cost_lookup",
        """
path = "/cost_lookup"
title = "Cost lookup by date"
returns = "relation"
cache_mode = "materialize"

[params]
as_of_date = "DATE"
product = "VARCHAR"
""".strip(),
        """
SELECT *
FROM base
WHERE product = $product AND as_of_date = $as_of_date
""".strip(),
    )

    build_dir = tmp_path / "build"
    compiled = compile_routes(tmp_path, build_dir)
    assert compiled[0].id == "cost_lookup"
    assert compiled[0].path == "/cost_lookup"
    param = compiled[0].find_param("product")
    assert param is not None
    assert param.extra.get("duckdb_type") == "VARCHAR"
    assert compiled[0].cache_mode == "materialize"
    assert compiled[0].returns == "relation"


def test_compile_rejects_orphan_sql(tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    (tmp_path / "lonely.sql").write_text("SELECT 1", encoding="utf-8")

    with pytest.raises(RouteCompilationError) as excinfo:
        compile_routes(tmp_path, build_dir)

    assert "Found SQL files without matching TOML" in str(excinfo.value)


def test_compile_parses_uses(tmp_path: Path) -> None:
    _write_pair(
        tmp_path,
        "parent",
        """
path = "/parent"

[[uses]]
alias = "child_view"
call = "child_route"
mode = "parquet_path"

[uses.args]
value = "filter_value"

[params]
filter_value = "VARCHAR"
""".strip(),
        """
SELECT *
FROM child_view
""".strip(),
    )

    build_dir = tmp_path / "build"
    compiled = compile_routes(tmp_path, build_dir)
    parent = compiled[0]
    assert parent.uses
    use = parent.uses[0]
    assert use.alias == "child_view"
    assert use.call == "child_route"
    assert use.mode == "parquet_path"
    assert use.args["value"] == "filter_value"


def test_compile_imports_legacy_markdown(tmp_path: Path) -> None:
    route_text = (
        "+++\n"
        "id = \"legacy\"\n"
        "path = \"/legacy\"\n"
        "+++\n\n"
        "```sql\nSELECT 1\n```\n"
    )
    legacy_path = write_route(tmp_path, route_text)
    build_dir = tmp_path / "build"
    compile_routes(tmp_path, build_dir)

    toml_path = legacy_path.with_suffix("").with_suffix(".toml")
    sql_path = legacy_path.with_suffix("").with_suffix(".sql")
    assert toml_path.exists()
    assert sql_path.exists()

def test_compile_extracts_directive_sections(tmp_path: Path) -> None:
    route_text = (
        "+++\n"
        "id = \"directive\"\n"
        "path = \"/directive\"\n"
        "[html_c]\n"
        "title_col = \"title\"\n"
        "+++\n\n"
        "<!-- @meta default_format=\"html_c\" allowed_formats=\"html_c json\" -->\n"
        "<!-- @preprocess {\"callable\": \"tests.fake:noop\"} -->\n"
        "<!-- @postprocess {\"html_c\": {\"image_col\": \"photo\"}} -->\n"
        "<!-- @charts [{\"id\": \"chart1\", \"type\": \"line\"}] -->\n"
        "<!-- @assets {\"image_getter\": \"static_fallback\"} -->\n"
        "```sql\nSELECT 'value' AS col\n```\n"
    )
    definition = compile_route_file(write_route(tmp_path, route_text))
    assert definition.default_format == "html_c"
    assert set(definition.allowed_formats) == {"html_c", "json"}
    assert definition.preprocess[0]["callable"] == "tests.fake:noop"
    assert definition.postprocess["html_c"]["image_col"] == "photo"
    assert definition.charts[0]["id"] == "chart1"
    assert definition.assets["image_getter"] == "static_fallback"


def test_compile_fails_without_sql(tmp_path: Path) -> None:
    toml_path = tmp_path / "broken.toml"
    toml_path.write_text("id = \"broken\"\npath = \"/broken\"\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        compile_route_file(toml_path)


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_server_returns_rows(tmp_path: Path) -> None:
    route_text = (
        "+++\n"
        "id = \"hello\"\n"
        "path = \"/hello\"\n"
        "[params.name]\n"
        "type = \"str\"\n"
        "required = false\n"
        "default = \"world\"\n"
        "[cache]\n"
        "order_by = [\"greeting\"]\n"
        "+++\n\n"
        "```sql\nSELECT 'Hello, ' || {{name}} || '!' AS greeting ORDER BY greeting\n```\n"
    )
    src_dir = tmp_path / "routes"
    src_dir.mkdir()
    write_route(src_dir, route_text)
    build_dir = tmp_path / "build"
    compile_routes(src_dir, build_dir)
    routes = load_compiled_routes(build_dir)
    app = create_app(routes, load_config(None))
    client = TestClient(app)

    response = client.get("/hello", params={"name": "DuckDB"})
    data = response.json()
    assert response.status_code == 200
    assert data["rows"][0]["greeting"] == "Hello, DuckDB!"

    html_response = client.get("/hello", params={"name": "DuckDB", "format": "html_t"})
    assert html_response.status_code == 200
    assert "Hello, DuckDB!" in html_response.text

    cards_response = client.get("/hello", params={"name": "DuckDB", "format": "html_c"})
    assert cards_response.status_code == 200
    assert "Hello, DuckDB!" in cards_response.text

    arrow_response = client.get("/hello", params={"name": "DuckDB", "format": "arrow", "limit": 1})
    assert arrow_response.status_code == 200
    assert arrow_response.headers["content-type"].startswith("application/vnd.apache.arrow.stream")

    feed_response = client.get("/hello", params={"name": "DuckDB", "format": "feed"})
    assert feed_response.status_code == 200
    assert "<section" in feed_response.text

    csv_response = client.get("/hello", params={"name": "DuckDB", "format": "csv"})
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv_response.headers["content-disposition"]

    parquet_response = client.get("/hello", params={"name": "DuckDB", "format": "parquet"})
    assert parquet_response.status_code == 200
    assert parquet_response.headers["content-type"].startswith("application/x-parquet")

    arrow_rpc = client.get("/hello", params={"name": "DuckDB", "format": "arrow_rpc", "limit": 1})
    assert arrow_rpc.status_code == 200
    assert arrow_rpc.headers["x-total-rows"] == "1"
    assert arrow_rpc.headers["x-offset"] == "0"

    analytics = client.get("/routes")
    assert analytics.status_code == 200
    payload = analytics.json()
    assert payload["routes"][0]["id"] == "hello"
