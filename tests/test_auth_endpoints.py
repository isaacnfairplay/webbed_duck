from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import write_sidecar_route
from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app
from webbed_duck.server.session import SESSION_COOKIE_NAME
from webbed_duck.server.vendor import CHARTJS_FILENAME

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    TestClient = None  # type: ignore


def _build_app(tmp_path: Path, *, auth_mode: str = "none"):
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    storage_root = tmp_path / "storage"
    src_dir.mkdir()
    storage_root.mkdir()

    route_text = (
        "+++\n"
        "id = \"ping\"\n"
        "path = \"/ping\"\n"
        "[cache]\n"
        "order_by = [\"value\"]\n"
        "+++\n\n"
        "```sql\nSELECT 1 AS value\n```\n"
    )
    write_sidecar_route(src_dir, "ping", route_text)
    compile_routes(src_dir, build_dir)
    routes = load_compiled_routes(build_dir)

    config = load_config(None)
    config.server.storage_root = storage_root
    config.auth.mode = auth_mode
    config.auth.allowed_domains = ["example.com"]

    return create_app(routes, config)


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_pseudo_session_lifecycle(tmp_path: Path) -> None:
    app = _build_app(tmp_path, auth_mode="pseudo")

    with TestClient(app, headers={"user-agent": "pytest"}) as client:
        create = client.post(
            "/auth/pseudo/session",
            json={"email": "user@example.com", "remember_me": True},
        )
        assert create.status_code == 200
        body = create.json()
        assert body["user"]["id"] == "user@example.com"
        cookie = create.cookies.get(SESSION_COOKIE_NAME)
        assert cookie
        header = create.headers["set-cookie"]
        assert "HttpOnly" in header
        assert "SameSite=lax" in header

        me = client.get("/auth/pseudo/session")
        assert me.status_code == 200
        me_payload = me.json()
        assert me_payload["user"]["display_name"] == "user"

        delete = client.delete("/auth/pseudo/session")
        assert delete.status_code == 200
        assert delete.json() == {"deleted": True}
        delete_header = delete.headers["set-cookie"]
        assert "Max-Age=0" in delete_header

        unauth = client.get("/auth/pseudo/session")
        assert unauth.status_code == 401


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_pseudo_session_rejects_invalid_payload(tmp_path: Path) -> None:
    app = _build_app(tmp_path, auth_mode="pseudo")

    with TestClient(app, headers={"user-agent": "pytest"}) as client:
        bad_domain = client.post(
            "/auth/pseudo/session",
            json={"email": "user@other.com"},
        )
        assert bad_domain.status_code == 400
        detail = bad_domain.json()["detail"]
        assert detail["code"] == "invalid_parameter"
        assert "domain" in detail["message"].lower()

        missing_body = client.post(
            "/auth/pseudo/session",
            content="null",
            headers={"content-type": "application/json", "user-agent": "pytest"},
        )
        assert missing_body.status_code == 400
        assert missing_body.json()["detail"]["code"] == "invalid_parameter"


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_chartjs_vendor_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEBDUCK_SKIP_CHARTJS_DOWNLOAD", raising=False)
    app = _build_app(tmp_path)

    asset_path = app.state.chartjs_asset_path
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_text("console.log('chart');", encoding="utf-8")

    with TestClient(app) as client:
        response = client.get(f"/vendor/{CHARTJS_FILENAME}")
        assert response.status_code == 200
        assert response.text == "console.log('chart');"


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_chartjs_vendor_route_missing_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBDUCK_SKIP_CHARTJS_DOWNLOAD", "1")
    app = _build_app(tmp_path)

    with TestClient(app) as client:
        response = client.get(f"/vendor/{CHARTJS_FILENAME}")
        assert response.status_code == 404
        payload = response.json()
        assert payload["detail"]["code"] == "not_found"

