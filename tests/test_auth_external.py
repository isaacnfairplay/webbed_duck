from pathlib import Path

import pytest

from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app

try:
    from fastapi.testclient import TestClient
except (ModuleNotFoundError, RuntimeError):  # pragma: no cover - optional dependency
    TestClient = None  # type: ignore


ROUTE = """
+++
id = "external"
path = "/external"
+++

```sql
SELECT 'ok' AS status;
```
"""


def _build_app(tmp_path: Path, configure) -> "TestClient":
    src = tmp_path / "src"
    build = tmp_path / "build"
    storage = tmp_path / "storage"
    src.mkdir()
    (src / "external.sql.md").write_text(ROUTE, encoding="utf-8")
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = storage
    configure(config)
    app = create_app(routes, config)
    if TestClient is None:  # pragma: no cover
        raise RuntimeError("fastapi test client unavailable")
    return TestClient(app)


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_proxy_auth_adapter_allows_shares(tmp_path: Path) -> None:
    def configure(config) -> None:
        config.auth.mode = "proxy"
        config.auth.proxy_header_user = "x-user-id"
        config.auth.proxy_header_email = "x-user-email"
        config.auth.allowed_domains = ["example.com"]

    client = _build_app(tmp_path, configure)

    response = client.post(
        "/shares",
        json={"route_id": "external"},
        headers={"x-user-id": "proxy-user", "x-user-email": "owner@example.com", "user-agent": "Proxy/1.0"},
    )
    assert response.status_code == 200
    share = response.json()["share"]
    assert share["route_id"] == "external"


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_external_auth_adapter_factory(tmp_path: Path) -> None:
    def configure(config) -> None:
        config.auth.mode = "external"
        config.auth.external_adapter = "tests.helpers.external_auth:create_adapter"

    client = _build_app(tmp_path, configure)

    ping = client.get("/auth/external/ping")
    assert ping.status_code == 200
    assert ping.json()["external"] is True

    response = client.post("/shares", json={"route_id": "external"})
    assert response.status_code == 200
    share = response.json()["share"]
    assert share["route_id"] == "external"
