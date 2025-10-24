from pathlib import Path
import io
import zipfile
from typing import Callable

import pytest

from webbed_duck.config import Config, load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app
from tests.helpers import email_stub

try:
    from fastapi.testclient import TestClient
except (ModuleNotFoundError, RuntimeError):  # pragma: no cover - optional dependency
    TestClient = None  # type: ignore


ROUTE = """
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


def _setup_app(tmp_path: Path, configure: Callable[[Config], None] | None = None) -> "TestClient":
    src = tmp_path / "src"
    build = tmp_path / "build"
    storage = tmp_path / "storage"
    src.mkdir()
    (src / "hello.sql.md").write_text(ROUTE, encoding="utf-8")
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = storage
    if configure is not None:
        configure(config)
    app = create_app(routes, config)
    if TestClient is None:  # pragma: no cover - guard
        raise RuntimeError("fastapi test client unavailable")
    return TestClient(app)


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_share_link_flow(tmp_path: Path) -> None:
    client = _setup_app(tmp_path)

    login = client.post("/auth/pseudo/login", json={"email": "owner@example.com"})
    assert login.status_code == 200

    share = client.post("/shares", json={"route_id": "hello", "params": {"name": "team"}})
    assert share.status_code == 200
    share_token = share.json()["share"]["token"]

    client.cookies.clear()
    missing_agent = client.get(f"/shares/{share_token}", headers={"user-agent": ""})
    assert missing_agent.status_code == 403
    assert missing_agent.json()["detail"]["code"] == "user_agent_required"

    response = client.get(f"/shares/{share_token}", headers={"user-agent": "ShareBot/1.0"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"][0]["greeting"] == "Hello, team!"

    replay = client.get(f"/shares/{share_token}", headers={"user-agent": "ShareBot/1.0"})
    assert replay.status_code == 403
    assert replay.json()["detail"]["code"] in {"invalid_token", "share_used"}


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_share_email_flow(tmp_path: Path) -> None:
    def configure(config: Config) -> None:
        config.email.adapter = "custom:tests.helpers.email_stub.send_email"
        config.share.zip_attachments = True
        config.share.watermark = True

    email_stub.reset()
    client = _setup_app(tmp_path, configure=configure)

    login = client.post("/auth/pseudo/login", json={"email": "owner@example.com"})
    assert login.status_code == 200

    payload = {
        "route_id": "hello",
        "params": {"name": "team"},
        "email": {
            "to": ["recipient@example.com"],
            "subject": "Team update",
            "message": "See the latest greeting.",
            "attachments": ["csv", "parquet"],
            "base_url": "https://example.com",
        },
    }
    response = client.post("/shares", json=payload)
    assert response.status_code == 200
    body = response.json()["share"]
    assert body["email"]["recipients"] == ["recipient@example.com"]
    assert body["email"]["share_url"].startswith("https://example.com/shares/")

    assert email_stub.sent_emails
    message = email_stub.sent_emails[-1]
    assert message["to"] == ["recipient@example.com"]
    assert "https://example.com/shares/" in message["html"]
    attachments = message["attachments"]
    assert len(attachments) == 1
    name, data = attachments[0]
    assert name.endswith("_share.zip")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = sorted(archive.namelist())
    assert "hello.csv" in names
    assert "hello.parquet" in names
