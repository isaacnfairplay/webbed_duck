from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
import pyarrow as pa

from tests.conftest import write_sidecar_route
from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import RouteDefinition, load_compiled_routes
from webbed_duck.server.app import create_app
from webbed_duck.server import cache as cache_mod

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    TestClient = None  # type: ignore


def test_cache_store_respects_configured_storage_root(tmp_path: Path) -> None:
    storage_root = tmp_path / "custom-root" / "nested"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[server]
storage_root = "{storage_root.as_posix()}"
""".strip(),
        encoding="utf-8",
    )
    config = load_config(config_path)

    assert config.server.storage_root == storage_root

    store = cache_mod.CacheStore(config.server.storage_root)

    expected_cache_dir = storage_root / "cache"
    assert store._root == expected_cache_dir
    assert expected_cache_dir.is_dir()


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_cache_files_materialize_under_configured_storage_root(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    storage_root = tmp_path / "custom-storage"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[server]
storage_root = "{storage_root.as_posix()}"
""".strip(),
        encoding="utf-8",
    )
    route_text = (
        "+++\n"
        "id = \"config-cache\"\n"
        "path = \"/config-cache\"\n"
        "title = \"Config cache\"\n"
        "[cache]\n"
        "order_by = [\"bird\"]\n"
        "rows_per_page = 1\n"
        "+++\n\n"
        "```sql\nSELECT 'duck' AS bird\n```\n"
    )
    write_sidecar_route(src, "config-cache", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(config_path)
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.get("/config-cache")
    assert response.status_code == 200

    cache_root = storage_root / "cache"
    route_cache_dir = cache_root / "config-cache"
    assert route_cache_dir.is_dir()
    parquet_pages = list(route_cache_dir.rglob("page-*.parquet"))
    assert parquet_pages

    cwd_cache_dir = Path.cwd() / "storage" / "cache" / "config-cache"
    assert not cwd_cache_dir.exists()


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_cache_hit_skips_duckdb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    route_text = (
        "+++\n"
        "id = \"cached\"\n"
        "path = \"/cached\"\n"
        "title = \"Cached\"\n"
        "[cache]\n"
        "order_by = [\"bird\"]\n"
        "rows_per_page = 1\n"
        "+++\n\n"
        "```sql\nSELECT 'duck' AS bird\n```\n"
    )
    write_sidecar_route(src, "cached", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    config.cache.page_rows = 1
    app = create_app(routes, config)
    client = TestClient(app)

    real_connect = duckdb.connect
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def counting_connect(*args, **kwargs):
        calls.append((args, kwargs))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(duckdb, "connect", counting_connect)

    first = client.get("/cached")
    assert first.status_code == 200
    second = client.get("/cached")
    assert second.status_code == 200
    assert len(calls) == 1


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_cache_enforces_row_limit(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    route_text = (
        "+++\n"
        "id = \"paged\"\n"
        "path = \"/paged\"\n"
        "title = \"Paged rows\"\n"
        "[cache]\n"
        "rows_per_page = 2\n"
        "order_by = [\"value\"]\n"
        "+++\n\n"
        "```sql\nSELECT range as value FROM range(0,5) ORDER BY value\n```\n"
    )
    write_sidecar_route(src, "paged", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    config.cache.page_rows = 2
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.get(
        "/paged",
        params={"format": "json", "limit": 1, "offset": 3},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["offset"] == 2
    assert payload["limit"] == 2
    assert payload["row_count"] == 2
    values = [row["value"] for row in payload["rows"]]
    assert values == [2, 3]


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_cache_respects_enforce_page_size_false(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    route_text = (
        "+++\n"
        "id = \"flex\"\n"
        "path = \"/flex\"\n"
        "title = \"Flexible paging\"\n"
        "[cache]\n"
        "rows_per_page = 2\n"
        "enforce_page_size = false\n"
        "order_by = [\"value\"]\n"
        "+++\n\n"
        "```sql\nSELECT range as value FROM range(0,8) ORDER BY value\n```\n"
    )
    write_sidecar_route(src, "flex", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    config.cache.page_rows = 2
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.get(
        "/flex",
        params={"format": "json", "limit": 4, "offset": 1},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["offset"] == 1
    assert payload["limit"] == 4
    assert payload["row_count"] == 4
    values = [row["value"] for row in payload["rows"]]
    assert values == [1, 2, 3, 4]


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_invariant_filter_uses_superset_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    route_text = (
        "+++\n"
        "id = \"inventory\"\n"
        "path = \"/inventory\"\n"
        "title = \"Inventory\"\n"
        "[params.product_code]\n"
        "type = \"str\"\n"
        "required = false\n"
        "[cache]\n"
        "rows_per_page = 5\n"
        "invariant_filters = [ { param = \"product_code\", column = \"product_code\", separator = \",\" } ]\n"
        "order_by = [\"seq\"]\n"
        "+++\n\n"
        "```sql\n"
        "SELECT product_code, quantity, seq\n"
        "FROM (VALUES\n"
        "    ('widget', 4, 1),\n"
        "    ('gadget', 2, 2),\n"
        "    ('widget', 3, 3)\n"
        ") AS inventory(product_code, quantity, seq)\n"
        "WHERE product_code = COALESCE({{ product_code }}, product_code)\n"
        "ORDER BY seq\n"
        "```\n"
    )
    write_sidecar_route(src, "inventory", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    app = create_app(routes, config)
    client = TestClient(app)

    real_connect = duckdb.connect
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def counting_connect(*args, **kwargs):
        calls.append((args, kwargs))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(duckdb, "connect", counting_connect)

    first = client.get("/inventory", params={"format": "json"})
    assert first.status_code == 200
    assert len(calls) == 1

    second = client.get(
        "/inventory",
        params={"format": "json", "product_code": "gadget"},
    )
    assert second.status_code == 200
    assert len(calls) == 1
    payload = second.json()
    assert payload["total_rows"] == 1
    assert [row["product_code"] for row in payload["rows"]] == ["gadget"]
    assert [row["quantity"] for row in payload["rows"]] == [2]


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_invariant_filter_case_insensitive_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    route_text = (
        "+++\n"
        "id = \"inventory\"\n"
        "path = \"/inventory\"\n"
        "title = \"Inventory\"\n"
        "[params.product_code]\n"
        "type = \"str\"\n"
        "required = false\n"
        "[cache]\n"
        "rows_per_page = 5\n"
        "order_by = [\"seq\"]\n"
        "invariant_filters = [ { param = \"product_code\", column = \"product_code\", case_insensitive = true } ]\n"
        "+++\n\n"
        "```sql\n"
        "SELECT product_code, quantity, seq\n"
        "FROM (VALUES\n"
        "    ('Widget', 4, 1),\n"
        "    ('gadget', 2, 2),\n"
        "    ('widget', 3, 3)\n"
        ") AS inventory(product_code, quantity, seq)\n"
        "WHERE product_code = COALESCE({{ product_code }}, product_code)\n"
        "ORDER BY seq\n"
        "```\n"
    )
    write_sidecar_route(src, "inventory", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    app = create_app(routes, config)
    client = TestClient(app)

    real_connect = duckdb.connect
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def counting_connect(*args, **kwargs):
        calls.append((args, kwargs))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(duckdb, "connect", counting_connect)

    superset = client.get("/inventory", params={"format": "json"})
    assert superset.status_code == 200
    assert len(calls) == 1

    mixed_case = client.get(
        "/inventory",
        params={"format": "json", "product_code": "WiDgEt"},
    )
    assert mixed_case.status_code == 200
    assert len(calls) == 1
    payload = mixed_case.json()
    values = [row["product_code"] for row in payload["rows"]]
    assert values == ["Widget", "widget"]

    uppercase = client.get(
        "/inventory",
        params=[("format", "json"), ("product_code", "GADGET")],
    )
    assert uppercase.status_code == 200
    assert len(calls) == 1
    gadget_values = [row["product_code"] for row in uppercase.json()["rows"]]
    assert gadget_values == ["gadget"]


def test_invariant_filter_case_insensitive_handles_large_string() -> None:
    table = pa.table(
        {
            "product_code": pa.array(
                ["Widget", "widget", "Gadget"],
                type=pa.large_string(),
            )
        }
    )
    setting = cache_mod.InvariantFilterSetting(
        param="product_code",
        column="product_code",
        case_insensitive=True,
    )

    filtered = cache_mod._apply_invariant_filters(
        table,
        [setting],
        {"product_code": ["WiDgEt"]},
    )

    assert filtered.column("product_code").to_pylist() == ["Widget", "widget"]


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_invariant_filter_supports_null_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    route_text = (
        "+++\n"
        "id = \"inventory_nulls\"\n"
        "path = \"/inventory_nulls\"\n"
        "title = \"Inventory nulls\"\n"
        "[params.product_code]\n"
        "type = \"str\"\n"
        "required = false\n"
        "[cache]\n"
        "rows_per_page = 5\n"
        "invariant_filters = [ { param = \"product_code\", column = \"product_code\" } ]\n"
        "order_by = [\"seq\"]\n"
        "+++\n\n"
        "```sql\n"
        "SELECT product_code, seq\n"
        "FROM (VALUES\n"
        "    ('widget', 1),\n"
        "    (NULL, 2),\n"
        "    ('gadget', 3)\n"
        ") AS inventory(product_code, seq)\n"
        "WHERE product_code IS NOT DISTINCT FROM COALESCE(NULLIF({{ product_code }}, ''), product_code)\n"
        "ORDER BY seq\n"
        "```\n"
    )
    write_sidecar_route(src, "inventory_nulls", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    app = create_app(routes, config)
    client = TestClient(app)

    real_connect = duckdb.connect
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def counting_connect(*args, **kwargs):
        calls.append((args, kwargs))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(duckdb, "connect", counting_connect)

    superset = client.get("/inventory_nulls", params={"format": "json"})
    assert superset.status_code == 200
    assert len(calls) == 1

    payload = superset.json()
    assert [row["product_code"] for row in payload["rows"]] == ["widget", None, "gadget"]

    no_filter = client.get(
        "/inventory_nulls",
        params=[("format", "json"), ("product_code", "")],
    )
    assert no_filter.status_code == 200
    assert no_filter.json()["rows"] == payload["rows"]

    explicit_null = client.get(
        "/inventory_nulls",
        params=[("format", "json"), ("product_code", "__null__")],
    )
    assert explicit_null.status_code == 200
    assert len(calls) == 2
    explicit_rows = explicit_null.json()["rows"]
    assert explicit_rows == [{"product_code": None, "seq": 2}]

    repeated_null = client.get(
        "/inventory_nulls",
        params=[("format", "json"), ("product_code", "__null__")],
    )
    assert repeated_null.status_code == 200
    assert len(calls) == 2
    assert repeated_null.json()["rows"] == explicit_rows


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_invariant_combines_filtered_caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    route_text = (
        "+++\n"
        "id = \"inventory\"\n"
        "path = \"/inventory\"\n"
        "title = \"Inventory\"\n"
        "[params.product_code]\n"
        "type = \"str\"\n"
        "required = false\n"
        "[cache]\n"
        "rows_per_page = 5\n"
        "invariant_filters = [ { param = \"product_code\", column = \"product_code\", separator = \",\" } ]\n"
        "order_by = [\"seq\"]\n"
        "+++\n\n"
        "```sql\n"
        "SELECT product_code, quantity, seq\n"
        "FROM (VALUES\n"
        "    ('widget', 4, 1),\n"
        "    ('gadget', 2, 2),\n"
        "    ('widget', 3, 3)\n"
        ") AS inventory(product_code, quantity, seq)\n"
        "WHERE product_code = COALESCE({{ product_code }}, product_code)\n"
        "ORDER BY seq\n"
        "```\n"
    )
    write_sidecar_route(src, "inventory", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    app = create_app(routes, config)
    client = TestClient(app)

    real_connect = duckdb.connect
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def counting_connect(*args, **kwargs):
        calls.append((args, kwargs))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(duckdb, "connect", counting_connect)

    first = client.get(
        "/inventory",
        params={"format": "json", "product_code": "widget"},
    )
    assert first.status_code == 200
    assert len(calls) == 1

    second = client.get(
        "/inventory",
        params={"format": "json", "product_code": "gadget"},
    )
    assert second.status_code == 200
    assert len(calls) == 2

    combined = client.get(
        "/inventory",
        params={"format": "json", "product_code": "widget,gadget"},
    )
    assert combined.status_code == 200
    assert len(calls) == 2
    payload = combined.json()
    assert [row["seq"] for row in payload["rows"]] == [1, 2, 3]
    returned = {
        (row["product_code"], row["quantity"])
        for row in payload["rows"]
    }
    assert returned == {("widget", 4), ("widget", 3), ("gadget", 2)}


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_invariant_partial_cache_triggers_query(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    route_text = (
        "+++\n"
        "id = \"inventory_partial\"\n"
        "path = \"/inventory_partial\"\n"
        "title = \"Inventory partial\"\n"
        "[params.product_code]\n"
        "type = \"str\"\n"
        "required = false\n"
        "[cache]\n"
        "rows_per_page = 5\n"
        "order_by = [\"seq\"]\n"
        "invariant_filters = [ { param = \"product_code\", column = \"product_code\", separator = \",\" } ]\n"
        "+++\n\n"
        "```sql\n"
        "SELECT product_code, quantity, seq\n"
        "FROM (VALUES\n"
        "    ('widget', 4, 1),\n"
        "    ('gadget', 2, 2),\n"
        "    ('widget', 3, 3)\n"
        ") AS inventory(product_code, quantity, seq)\n"
        "WHERE product_code = COALESCE({{ product_code }}, product_code)\n"
        "ORDER BY seq\n"
        "```\n"
    )
    write_sidecar_route(src, "inventory_partial", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    app = create_app(routes, config)
    client = TestClient(app)

    real_connect = duckdb.connect
    calls: list[int] = []

    def counting_connect(*args, **kwargs):
        calls.append(1)
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(duckdb, "connect", counting_connect)

    first = client.get(
        "/inventory_partial",
        params={"format": "json", "product_code": "widget"},
    )
    assert first.status_code == 200
    assert len(calls) == 1

    second = client.get(
        "/inventory_partial",
        params={"format": "json", "product_code": "widget,gadget"},
    )
    assert second.status_code == 200
    assert len(calls) == 2

    third = client.get(
        "/inventory_partial",
        params={"format": "json", "product_code": "gadget"},
    )
    assert third.status_code == 200
    assert len(calls) == 3


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_invariant_filters_apply_to_html_views(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    route_text = (
        "+++\n"
        "id = \"division_map\"\n"
        "path = \"/division_map\"\n"
        "title = \"Division map\"\n"
        "description = \"Demonstrate invariant filters for HTML views\"\n"
        "[params.division]\n"
        "type = \"str\"\n"
        "default = \"\"\n"
        "required = false\n"
        "ui_label = \"Division\"\n"
        "ui_control = \"select\"\n"
        "options = [\"\", \"Engineering\", \"Finance\", \"Manufacturing\"]\n"
        "[cache]\n"
        "rows_per_page = 50\n"
        "order_by = [\"Division\", \"Department\", \"TeamCode\"]\n"
        "invariant_filters = [ { param = \"division\", column = \"Division\" } ]\n"
        "[html_t]\n"
        "show_params = [\"division\"]\n"
        "+++\n\n"
        "```sql\n"
        "SELECT * FROM (VALUES\n"
        "    ('ENG1', 'Mechanical Design', 'Engineering', 101),\n"
        "    ('ENG2', 'Electrical Systems', 'Engineering', 102),\n"
        "    ('FIN1', 'Payroll', 'Finance', 201),\n"
        "    ('MFG1', 'Assembly Line 1', 'Manufacturing', 301)\n"
        ") AS t(Department, Team, Division, TeamCode)\n"
        "ORDER BY Division, Department, TeamCode\n"
        "```\n"
    )
    write_sidecar_route(src, "division_map", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    app = create_app(routes, config)
    client = TestClient(app)

    json_response = client.get(
        "/division_map",
        params={"format": "json", "division": "Manufacturing"},
    )
    assert json_response.status_code == 200
    json_payload = json_response.json()
    assert [row["Division"] for row in json_payload["rows"]] == ["Manufacturing"]

    html_response = client.get(
        "/division_map",
        params={"format": "html_t", "division": "Manufacturing"},
    )
    assert html_response.status_code == 200
    html_text = html_response.text
    assert "Manufacturing" in html_text
    assert "<td>Engineering</td>" not in html_text
    assert "<td>Finance</td>" not in html_text


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_invariant_filters_coerce_numeric_strings(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    route_text = (
        "+++\n"
        "id = \"numeric_invariant\"\n"
        "path = \"/numeric_invariant\"\n"
        "title = \"Numeric invariant filters\"\n"
        "[params.OperationCode]\n"
        "type = \"str\"\n"
        "required = false\n"
        "ui_label = \"Operation\"\n"
        "[cache]\n"
        "rows_per_page = 50\n"
        "order_by = [\"RouteCode\", \"OperationCode\"]\n"
        "invariant_filters = [ { param = \"OperationCode\", column = \"OperationCode\" } ]\n"
        "+++\n\n"
        "```sql\n"
        "SELECT * FROM (VALUES\n"
        "    ('A', 0),\n"
        "    ('A', 10),\n"
        "    ('B', 20)\n"
        ") AS t(RouteCode, OperationCode)\n"
        "ORDER BY RouteCode, OperationCode\n"
        "```\n"
    )
    write_sidecar_route(src, "numeric_invariant", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    app = create_app(routes, config)
    client = TestClient(app)

    ten_response = client.get(
        "/numeric_invariant",
        params={"format": "json", "OperationCode": "10"},
    )
    assert ten_response.status_code == 200
    ten_payload = ten_response.json()
    assert [row["OperationCode"] for row in ten_payload["rows"]] == [10]

    zero_response = client.get(
        "/numeric_invariant",
        params={"format": "json", "OperationCode": "0"},
    )
    assert zero_response.status_code == 200
    zero_payload = zero_response.json()
    assert [row["OperationCode"] for row in zero_payload["rows"]] == [0]


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_invariant_select_defaults_to_unique_values(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    route_text = (
        "+++\n"
        "id = \"invariant_select_default\"\n"
        "path = \"/invariant_select_default\"\n"
        "title = \"Division selector\"\n"
        "[params.division]\n"
        "type = \"str\"\n"
        "default = \"\"\n"
        "ui_label = \"Division\"\n"
        "ui_control = \"select\"\n"
        "[cache]\n"
        "rows_per_page = 50\n"
        "order_by = [\"Division\", \"Department\"]\n"
        "invariant_filters = [ { param = \"division\", column = \"Division\" } ]\n"
        "[html_t]\n"
        "show_params = [\"division\"]\n"
        "+++\n\n"
        "```sql\n"
        "SELECT * FROM (VALUES\n"
        "    ('ENG', 'Engineering', 'Mechanical Design'),\n"
        "    ('FIN', 'Finance', 'Payroll'),\n"
        "    ('MFG', 'Manufacturing', 'Assembly')\n"
        ") AS t(Code, Division, Department)\n"
        "WHERE {{ division }} = '' OR Division = {{ division }}\n"
        "ORDER BY Division\n"
        "```\n"
    )
    write_sidecar_route(src, "invariant_select_default", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.get("/invariant_select_default", params={"format": "html_t"})
    assert response.status_code == 200
    text = response.text
    assert "<option value='' selected>" in text
    assert "<option value='Engineering'>Engineering</option>" in text
    assert "<option value='Finance'>Finance</option>" in text
    assert "<option value='Manufacturing'>Manufacturing</option>" in text


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_invariant_html_form_filters_after_numeric_selection(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    route_text = (
        "+++\n"
        "id = \"invariant_year_division\"\n"
        "path = \"/invariant_year_division\"\n"
        "title = \"Year and division selector\"\n"
        "[params.year]\n"
        "type = \"str\"\n"
        "default = \"\"\n"
        "ui_label = \"Year\"\n"
        "ui_control = \"select\"\n"
        "[params.division]\n"
        "type = \"str\"\n"
        "default = \"\"\n"
        "ui_label = \"Division\"\n"
        "ui_control = \"select\"\n"
        "[cache]\n"
        "rows_per_page = 10\n"
        "order_by = [\"Year\", \"Division\"]\n"
        "invariant_filters = [\n"
        "    { param = \"year\", column = \"Year\" },\n"
        "    { param = \"division\", column = \"Division\" },\n"
        "]\n"
        "[html_t]\n"
        "show_params = [\"year\", \"division\"]\n"
        "+++\n\n"
        "```sql\n"
        "SELECT * FROM (VALUES\n"
        "    (2023, 'Engineering', 'ENG-01'),\n"
        "    (2023, 'Finance', 'FIN-02'),\n"
        "    (2024, 'Engineering', 'ENG-10'),\n"
        "    (2024, 'Operations', 'OPS-11')\n"
        ") AS t(Year, Division, Code)\n"
        "WHERE ({{ year }} = '' OR Year = CAST({{ year }} AS INTEGER))\n"
        "  AND ({{ division }} = '' OR Division = {{ division }})\n"
        "ORDER BY Year, Division\n"
        "```\n"
    )
    write_sidecar_route(src, "invariant_year_division", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    app = create_app(routes, config)
    client = TestClient(app)

    json_response = client.get(
        "/invariant_year_division",
        params={"format": "json", "year": "2024"},
    )
    assert json_response.status_code == 200
    payload = json_response.json()
    assert [row["Year"] for row in payload["rows"]] == [2024, 2024]
    assert [row["Division"] for row in payload["rows"]] == ["Engineering", "Operations"]

    html_response = client.get(
        "/invariant_year_division",
        params={"format": "html_t", "year": "2024"},
    )
    assert html_response.status_code == 200
    text = html_response.text
    assert "<option value='2024' selected>2024</option>" in text
    assert "<option value='Engineering'>Engineering</option>" in text
    assert "<option value='Operations'>Operations</option>" in text
    assert "<option value='Finance'>Finance</option>" not in text


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_html_filters_render_for_invariants_without_params(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    route_text = (
        "+++\n"
        "id = \"auto_invariants\"\n"
        "path = \"/auto_invariants\"\n"
        "title = \"Auto invariants\"\n"
        "[cache]\n"
        "rows_per_page = 50\n"
        "order_by = [\"Division\", \"Department\"]\n"
        "invariant_filters = [ { param = \"division\", column = \"Division\", ui_label = \"Division\" } ]\n"
        "[html_t]\n"
        "show_params = [\"division\"]\n"
        "+++\n\n"
        "```sql\n"
        "SELECT * FROM (VALUES\n"
        "    ('Engineering', 'ENG'),\n"
        "    ('Finance', 'FIN'),\n"
        "    ('Manufacturing', 'MFG')\n"
        ") AS t(Division, Department)\n"
        "ORDER BY Division\n"
        "```\n"
    )
    write_sidecar_route(src, "auto_invariants", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    app = create_app(routes, config)
    client = TestClient(app)

    json_response = client.get(
        "/auto_invariants",
        params={"format": "json", "division": "Finance"},
    )
    assert json_response.status_code == 200
    payload = json_response.json()
    divisions = [row["Division"] for row in payload["rows"]]
    assert divisions == ["Finance"]

    html_response = client.get(
        "/auto_invariants",
        params={"format": "html_t", "division": "Finance"},
    )
    assert html_response.status_code == 200
    html_text = html_response.text
    assert "<td>Finance</td>" in html_text
    assert "<td>Engineering</td>" not in html_text
    assert ("name='division'" in html_text) or ("name=\"division\"" in html_text)


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_invariant_unique_values_respect_filter_context(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    route_text = (
        "+++\n"
        "id = \"invariant_select_linked\"\n"
        "path = \"/invariant_select_linked\"\n"
        "title = \"Division and department\"\n"
        "[params.division]\n"
        "type = \"str\"\n"
        "default = \"\"\n"
        "ui_label = \"Division\"\n"
        "ui_control = \"select\"\n"
        "[params.department]\n"
        "type = \"str\"\n"
        "default = \"\"\n"
        "ui_label = \"Department\"\n"
        "ui_control = \"select\"\n"
        "options = \"...unique_values...\"\n"
        "[cache]\n"
        "rows_per_page = 50\n"
        "order_by = [\"Division\", \"Department\"]\n"
        "invariant_filters = [\n"
        "  { param = \"division\", column = \"Division\" },\n"
        "  { param = \"department\", column = \"Department\" }\n"
        "]\n"
        "[html_t]\n"
        "show_params = [\"division\", \"department\"]\n"
        "+++\n\n"
        "```sql\n"
        "SELECT * FROM (VALUES\n"
        "    ('Engineering', 'Mechanical Design'),\n"
        "    ('Engineering', 'Electrical Systems'),\n"
        "    ('Finance', 'Payroll'),\n"
        "    ('Manufacturing', 'Assembly Line 1')\n"
        ") AS t(Division, Department)\n"
        "WHERE {{ division }} = '' OR Division = {{ division }}\n"
        "ORDER BY Division, Department\n"
        "```\n"
    )
    write_sidecar_route(src, "invariant_select_linked", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.get(
        "/invariant_select_linked",
        params={"format": "html_t", "division": "Engineering"},
    )
    assert response.status_code == 200
    text = response.text
    assert "<option value='Engineering' selected>Engineering</option>" in text
    department_select_start = text.index("<select id='param-department'")
    department_select_end = text.index("</select>", department_select_start)
    department_block = text[department_select_start:department_select_end]
    assert "Mechanical Design" in department_block
    assert "Electrical Systems" in department_block
    assert "Payroll" not in department_block
    assert "Assembly Line 1" not in department_block


def test_normalize_invariant_value_interprets_null_tokens() -> None:
    setting = cache_mod.InvariantFilterSetting(param="code", column="code")

    assert cache_mod.normalize_invariant_value("", setting) == []
    assert cache_mod.normalize_invariant_value("__null__", setting) == [None]
    assert cache_mod.normalize_invariant_value("__NULL__", setting) == [None]
    assert cache_mod.normalize_invariant_value(["", "widget"], setting) == ["widget"]

    multi_setting = cache_mod.InvariantFilterSetting(param="code", column="code", separator=",")
    assert cache_mod.normalize_invariant_value("widget, __null__ , gadget", multi_setting) == [
        "widget",
        None,
        "gadget",
    ]


def test_canonicalize_invariant_value_normalizes_decimals() -> None:
    setting = cache_mod.InvariantFilterSetting(param="amount", column="amount")

    token = cache_mod.canonicalize_invariant_value(Decimal("1.00"), setting)
    assert token.startswith("num:")
    assert token == cache_mod.canonicalize_invariant_value(Decimal("1.0"), setting)
    assert token == cache_mod.canonicalize_invariant_value(Decimal("1"), setting)


def test_canonicalize_invariant_value_aligns_numeric_types() -> None:
    setting = cache_mod.InvariantFilterSetting(param="amount", column="amount")

    base = cache_mod.canonicalize_invariant_value(1, setting)

    assert base == cache_mod.canonicalize_invariant_value(1.0, setting)
    assert base == cache_mod.canonicalize_invariant_value(Decimal("1.0"), setting)


def test_canonicalize_invariant_value_normalizes_negative_zero() -> None:
    setting = cache_mod.InvariantFilterSetting(param="amount", column="amount")

    assert cache_mod.canonicalize_invariant_value(-0.0, setting) == cache_mod.canonicalize_invariant_value(
        0, setting
    )
    assert cache_mod.canonicalize_invariant_value(-0.0, setting) == cache_mod.canonicalize_invariant_value(
        Decimal("0"), setting
    )


def test_canonicalize_invariant_mapping_collapses_decimal_variants() -> None:
    setting = cache_mod.InvariantFilterSetting(param="amount", column="amount")
    mapping = cache_mod.canonicalize_invariant_mapping(
        {"amount": (Decimal("2.500"), Decimal("2.50"))},
        [setting],
    )

    assert mapping == {"amount": [cache_mod.canonicalize_invariant_value(Decimal("2.5"), setting)]}


def test_canonicalize_invariant_mapping_collapses_numeric_variants() -> None:
    setting = cache_mod.InvariantFilterSetting(param="amount", column="amount")

    mapping = cache_mod.canonicalize_invariant_mapping(
        {"amount": (1, 1.0, Decimal("1.00"), Decimal("1"), -0.0, 0)},
        [setting],
    )

    expected_tokens = {
        cache_mod.canonicalize_invariant_value(Decimal("1"), setting),
        cache_mod.canonicalize_invariant_value(Decimal("0"), setting),
    }

    assert mapping == {"amount": sorted(expected_tokens)}


def test_cache_key_ignores_invariant_order(tmp_path: Path) -> None:
    store = cache_mod.CacheStore(tmp_path)
    route = RouteDefinition(
        id="inventory",
        path="/inventory",
        methods=("GET",),
        raw_sql="SELECT 1",
        prepared_sql="SELECT 1",
        param_order=("product_code",),
        params=(),
        metadata={},
        version="v1",
    )

    first = cache_mod.InvariantFilterSetting(param="product_code", column="product_code")
    second = cache_mod.InvariantFilterSetting(param="region", column="region", case_insensitive=True)

    params = {"product_code": "widget", "region": "EMEA"}

    base_settings = dict(
        enabled=True,
        ttl_seconds=3600,
        rows_per_page=10,
        enforce_page_size=True,
        order_by=("product_code",),
    )

    key_a = store.compute_key(
        route,
        params,
        cache_mod.CacheSettings(invariant_filters=(first, second), **base_settings),
    )
    key_b = store.compute_key(
        route,
        params,
        cache_mod.CacheSettings(invariant_filters=(second, first), **base_settings),
    )

    assert key_a.digest == key_b.digest


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_invariant_unique_values_merge_with_static_options(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    route_text = (
        "+++\n"
        "id = \"invariant_select_prefill\"\n"
        "path = \"/invariant_select_prefill\"\n"
        "title = \"Division selector\"\n"
        "[params.division]\n"
        "type = \"str\"\n"
        "default = \"\"\n"
        "ui_label = \"Division\"\n"
        "ui_control = \"select\"\n"
        "options = [\"...unique_values...\", { value = \"Other\", label = \"Custom\" }]\n"
        "[cache]\n"
        "rows_per_page = 50\n"
        "order_by = [\"Division\"]\n"
        "invariant_filters = [ { param = \"division\", column = \"Division\" } ]\n"
        "[html_t]\n"
        "show_params = [\"division\"]\n"
        "+++\n\n"
        "```sql\n"
        "SELECT * FROM (VALUES\n"
        "    ('ENG', 'Engineering'),\n"
        "    ('FIN', 'Finance')\n"
        ") AS t(Code, Division)\n"
        "WHERE {{ division }} = '' OR Division = {{ division }}\n"
        "ORDER BY Division\n"
        "```\n"
    )
    write_sidecar_route(src, "invariant_select_prefill", route_text)
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.get("/invariant_select_prefill", params={"format": "html_t"})
    assert response.status_code == 200
    text = response.text
    assert "<option value='' selected>" in text
    assert "<option value='Engineering'>Engineering</option>" in text
    assert "<option value='Finance'>Finance</option>" in text
    assert "<option value='Other'>Custom</option>" in text
from decimal import Decimal
