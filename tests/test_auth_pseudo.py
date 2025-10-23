from __future__ import annotations

from pathlib import Path

import pytest

from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app
from webbed_duck.server.auth import SESSION_COOKIE

pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402  (import guarded by importorskip)


def _write_route(tmp_path: Path) -> None:
    content = (
        "+++\n"
        "id = \"auth_test\"\n"
        "path = \"/auth-test\"\n"
        "+++\n\n"
        "```sql\nSELECT 1 AS value\n```\n"
    )
    (tmp_path / "sample.sql.md").write_text(content, encoding="utf-8")


def _make_app(tmp_path: Path) -> TestClient:
    source = tmp_path / "src"
    build = tmp_path / "build"
    storage = tmp_path / "storage"
    source.mkdir()
    _write_route(source)
    compile_routes(source, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = storage
    config.auth.mode = "pseudo"
    config.auth.allowed_domains = ["example.com"]
    client = TestClient(create_app(routes, config))
    return client


def test_pseudo_auth_login_and_me(tmp_path: Path) -> None:
    client = _make_app(tmp_path)

    response = client.post(
        "/auth/pseudo/login",
        json={"email": "user@example.com", "display_name": "Test User"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["user_id"].startswith(payload["user"]["email_hash"][:8])

    me = client.get("/auth/me")
    assert me.status_code == 200
    details = me.json()["user"]
    assert details["email"] == "user@example.com"
    assert details["display_name"] == "Test User"


def test_pseudo_auth_respects_domain_allowlist(tmp_path: Path) -> None:
    client = _make_app(tmp_path)

    bad = client.post("/auth/pseudo/login", json={"email": "user@other.com"})
    assert bad.status_code == 403
    assert bad.json()["detail"]["code"] == "domain_not_allowed"


def test_pseudo_auth_logout_clears_session(tmp_path: Path) -> None:
    client = _make_app(tmp_path)

    response = client.post("/auth/pseudo/login", json={"email": "user@example.com"})
    assert response.status_code == 200
    assert SESSION_COOKIE in client.cookies

    logout = client.post("/auth/pseudo/logout")
    assert logout.status_code == 200
    assert logout.json()["logged_out"] is True
    assert SESSION_COOKIE not in client.cookies

    unauthorized = client.get("/auth/me")
    assert unauthorized.status_code == 401

