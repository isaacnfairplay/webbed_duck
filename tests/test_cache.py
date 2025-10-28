from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tests.conftest import write_sidecar_route
from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    TestClient = None  # type: ignore


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
