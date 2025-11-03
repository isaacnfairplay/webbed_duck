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
id = "append_demo"
path = "/append_demo"
[append]
columns = ["value"]
destination = "logs/data.csv"
+++

```sql
SELECT 1 AS value
```
"""


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_append_requires_object_payload(tmp_path: Path) -> None:
    client = build_test_client(tmp_path, "append_demo", _ROUTE_SOURCE)
    try:
        response = client.post(
            "/routes/append_demo/append",
            json=[{"value": 1}],
        )
    finally:
        client.close()
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_parameter"
    assert detail["message"] == "Append payload must be an object"
    assert detail["category"] == "ValidationError"
    assert (
        detail["hint"]
        == "Verify the value is formatted as documented (e.g. integer, boolean)."
    )
