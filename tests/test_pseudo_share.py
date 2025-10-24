from __future__ import annotations

import sqlite3
import sys
import types
from pathlib import Path

import pytest

from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app
from webbed_duck.server.session import SESSION_COOKIE_NAME

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    TestClient = None  # type: ignore


ROUTE_TEXT = """
+++
id = "hello"
path = "/hello"
[params.name]
type = "str"
required = false
default = "world"
+++

```sql
SELECT 'Hello, ' || {{name}} || '!' AS greeting;
```
"""


def _prepare_app(tmp_path: Path, email_module: str, *, route_text: str = ROUTE_TEXT) -> TestClient:
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    storage_root = tmp_path / "storage"
    src_dir.mkdir()
    (src_dir / "hello.sql.md").write_text(route_text, encoding="utf-8")
    compile_routes(src_dir, build_dir)
    routes = load_compiled_routes(build_dir)
    config = load_config(None)
    config.server.storage_root = storage_root
    config.auth.mode = "pseudo"
    config.auth.allowed_domains = ["example.com"]
    config.email.adapter = f"{email_module}:send_email"
    config.email.bind_share_to_user_agent = False
    config.email.bind_share_to_ip_prefix = False
    app = create_app(routes, config)
    return TestClient(app)


def _install_email_adapter(records: list[tuple]) -> str:
    module_name = "tests.email_capture"
    module = types.ModuleType(module_name)

    def send_email(to_addrs, subject, html_body, text_body=None, attachments=None):
        records.append((tuple(to_addrs), subject, html_body, text_body, attachments))

    module.send_email = send_email  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    return module_name


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_pseudo_auth_sessions_and_share(tmp_path: Path) -> None:
    records: list[tuple] = []
    module_name = _install_email_adapter(records)
    client = _prepare_app(tmp_path, module_name)

    login = client.post("/auth/pseudo/session", json={"email": "user@example.com"})
    assert login.status_code == 200
    assert SESSION_COOKIE_NAME in login.cookies

    share = client.post(
        "/routes/hello/share",
        json={"emails": ["friend@example.com"], "params": {"name": "Duck"}, "format": "json"},
    )
    assert share.status_code == 200
    data = share.json()["share"]
    assert "token" in data and data["format"] == "json"
    assert len(records) == 1
    sent = records[0]
    assert "friend@example.com" in sent[0]
    assert sent[4] is None  # no attachments by default
    assert "webbed_duck share" in sent[2]

    token = data["token"]
    shared = client.get(f"/shares/{token}")
    assert shared.status_code == 200
    payload = shared.json()
    assert payload["rows"][0]["greeting"] == "Hello, Duck!"
    assert payload["total_rows"] == 1

    share_meta = share.json()["share"]
    assert share_meta["attachments"] == []
    assert share_meta["inline_snapshot"] is True
    assert share_meta["rows_shared"] == 1
    assert share_meta["redacted_columns"] == []
    assert share_meta["watermark"] is True
    assert share_meta["zipped"] is False

    db_path = tmp_path / "storage" / "runtime" / "meta.sqlite3"
    with sqlite3.connect(db_path) as conn:
        share_row = conn.execute("SELECT token_hash FROM shares").fetchone()
        session_row = conn.execute("SELECT token_hash FROM sessions").fetchone()
    assert share_row is not None and share_row[0] != token
    assert session_row is not None and session_row[0] != login.cookies[SESSION_COOKIE_NAME]

ROUTE_ATTACH_TEXT = (
    "+++\n"
    "id = \"report\"\n"
    "path = \"/report\"\n"
    "[params.name]\n"
    "type = \"str\"\n"
    "required = false\n"
    "default = \"world\"\n\n"
    "[share]\n"
    "pii_columns = [\"email\"]\n"
    "+++\n\n"
    "```sql\n"
    "SELECT\n"
    "  'Hello, ' || {{name}} || '!' AS greeting,\n"
    "  'sensitive@example.com' AS email,\n"
    "  'note' AS note\n"
    "UNION ALL\n"
    "SELECT\n"
    "  'Hello, friend!' AS greeting,\n"
    "  'friend@example.com' AS email,\n"
    "  'another' AS note;\n"
    "```\n"
)


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_share_with_attachments_and_redaction(tmp_path: Path) -> None:
    records: list[tuple] = []
    module_name = _install_email_adapter(records)
    client = _prepare_app(tmp_path, module_name, route_text=ROUTE_ATTACH_TEXT)

    login = client.post("/auth/pseudo/session", json={"email": "user@example.com"})
    assert login.status_code == 200

    response = client.post(
        "/routes/report/share",
        json={
            "emails": ["friend@example.com"],
            "params": {"name": "Duck"},
            "format": "html_t",
            "attachments": ["csv", "html"],
            "inline_snapshot": False,
            "zip": True,
            "zip_passphrase": "secret",
            "redact_pii": True,
            "max_rows": 1,
        },
    )
    assert response.status_code == 200
    share = response.json()["share"]
    token = share["token"]
    assert share["attachments"] and share["attachments"][0].endswith(".zip")
    assert share["zipped"] is True
    assert share["inline_snapshot"] is False
    assert share["rows_shared"] == 1
    assert "email" in share["redacted_columns"]
    assert share["watermark"] is True

    resolved = client.get(f"/shares/{token}?format=json")
    assert resolved.status_code == 200
    resolved_payload = resolved.json()
    assert "email" not in resolved_payload["columns"]
    assert all("email" not in row for row in resolved_payload["rows"])

    assert len(records) == 1
    _, _, _, _, attachments = records[-1]
    assert attachments and attachments[0][0].endswith(".zip")
