from __future__ import annotations

from pathlib import Path

import pytest

from tests.http._helpers import build_test_client

try:  # pragma: no cover - optional dependency guard
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover
    TestClient = None  # type: ignore


_ROUTE_SOURCE = """
+++
id = "share_demo"
path = "/share_demo"
cache_mode = "passthrough"
default_format = "html_t"
+++

```sql
SELECT 1 AS id, 'hello' AS greeting
```
"""


def _configure_pseudo(config) -> None:
    config.auth.mode = "pseudo"
    config.auth.allowed_domains = ["example.com"]


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_share_params_must_be_mapping(pseudo_session_factory, tmp_path: Path) -> None:
    client = build_test_client(tmp_path, "share_demo", _ROUTE_SOURCE, configure=_configure_pseudo)
    helper = pseudo_session_factory(client)
    helper.issue()
    try:
        response = client.post(
            "/routes/share_demo/share",
            json={"params": "name", "emails": ["friend@example.com"]},
        )
    finally:
        client.close()
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_parameter"
    assert detail["message"] == "Share params must be an object"
    assert detail["category"] == "ValidationError"
    assert (
        detail["hint"]
        == "Verify the value is formatted as documented (e.g. integer, boolean)."
    )


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_share_reports_email_adapter_failure(
    failing_email_sender, pseudo_session_factory, tmp_path: Path
) -> None:
    client = build_test_client(tmp_path, "share_demo", _ROUTE_SOURCE, configure=_configure_pseudo)
    helper = pseudo_session_factory(client)
    helper.issue()
    failing_email_sender(client.app, RuntimeError("smtp offline"))
    try:
        response = client.post(
            "/routes/share_demo/share",
            json={"params": {}, "emails": ["friend@example.com"]},
        )
    finally:
        client.close()
    detail = response.json()["detail"]
    assert response.status_code == 502, detail
    assert detail["code"] == "email_failed"
    assert "smtp offline" in detail["message"]


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_share_rejects_expired_session(pseudo_session_factory, tmp_path: Path) -> None:
    client = build_test_client(tmp_path, "share_demo", _ROUTE_SOURCE, configure=_configure_pseudo)
    helper = pseudo_session_factory(client)
    record = helper.issue(expired=True)
    try:
        response = client.post(
            "/routes/share_demo/share",
            json={"params": {}, "emails": ["friend@example.com"]},
        )
    finally:
        client.close()
    assert response.status_code == 401
    detail = response.json()["detail"]
    assert detail["code"] == "not_authenticated"
    store = client.app.state.session_store
    resolved = store.resolve(
        record.token,
        user_agent=client.headers.get("user-agent"),
        ip_address=None,
    )
    assert resolved is None
