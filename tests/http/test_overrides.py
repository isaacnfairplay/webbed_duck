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
id = "override_demo"
path = "/override_demo"
[overrides]
key_columns = ["id"]
allowed = ["status"]
+++

```sql
SELECT 1 AS id, 'pending' AS status
```
"""


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_save_override_requires_column(tmp_path: Path) -> None:
    client = build_test_client(tmp_path, "override_demo", _ROUTE_SOURCE)
    try:
        response = client.post(
            "/routes/override_demo/overrides",
            json={"column": "  ", "row_key": "1"},
        )
    finally:
        client.close()
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_parameter"
    assert detail["message"] == "Override column is required"
    assert detail["category"] == "ValidationError"
    assert (
        detail["hint"]
        == "Verify the value is formatted as documented (e.g. integer, boolean)."
    )


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_save_override_requires_key_payload(tmp_path: Path) -> None:
    client = build_test_client(tmp_path, "override_demo", _ROUTE_SOURCE)
    try:
        response = client.post(
            "/routes/override_demo/overrides",
            json={"column": "status"},
        )
    finally:
        client.close()
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "missing_parameter"
    assert detail["message"] == "Provide either row_key or key mapping"
    assert detail["category"] == "ValidationError"
    assert detail["hint"] == "Ensure the query string includes the documented parameter name."
