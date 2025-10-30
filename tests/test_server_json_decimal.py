from __future__ import annotations

from pathlib import Path

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


ROUTE_TEXT = """+++
id = \"decimal\"
path = \"/decimal\"
title = \"Decimal export\"
allowed_formats = [\"json\"]
[cache]
order_by = [\"amount\"]
rows_per_page = 10
+++

```sql
SELECT CAST(12.34 AS DECIMAL(10, 2)) AS amount
```
"""


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_json_response_serializes_decimal(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    storage_root = tmp_path / "storage"
    src_dir.mkdir()
    storage_root.mkdir()
    write_sidecar_route(src_dir, "decimal", ROUTE_TEXT)
    compile_routes(src_dir, build_dir)
    routes = load_compiled_routes(build_dir)
    config = load_config(None)
    config.server.storage_root = storage_root
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.get("/decimal", params={"format": "json"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == [{"amount": "12.34"}]
    assert payload["columns"] == ["amount"]
