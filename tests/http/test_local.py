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
id = "local_demo"
path = "/local_demo"
+++

```sql
SELECT 1 AS id
```
"""


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_local_resolve_requires_json_object(analytics_toggle, tmp_path: Path) -> None:
    client = build_test_client(tmp_path, "local_demo", _ROUTE_SOURCE)
    analytics_toggle(client.app, enabled=False)
    try:
        response = client.post("/local/resolve", json=["invalid"])
    finally:
        client.close()
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_parameter"
    assert detail["message"] == "Request body must be a JSON object"
    assert detail["category"] == "ValidationError"
    assert (
        detail["hint"]
        == "Verify the value is formatted as documented (e.g. integer, boolean)."
    )


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_local_resolve_requires_reference_key(tmp_path: Path) -> None:
    client = build_test_client(tmp_path, "local_demo", _ROUTE_SOURCE)
    try:
        response = client.post("/local/resolve", json={})
    finally:
        client.close()
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "missing_parameter"
    assert detail["message"] == "reference is required"
    assert detail["category"] == "ValidationError"
    assert detail["hint"] == "Ensure the query string includes the documented parameter name."
