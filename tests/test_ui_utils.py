from __future__ import annotations

from decimal import Decimal

import json
import pyarrow as pa

from webbed_duck.server.ui.utils import table_to_records


def test_table_to_records_serializes_decimal() -> None:
    table = pa.table({"amount": pa.array([Decimal("12.34")], type=pa.decimal128(10, 2))})

    records = table_to_records(table)

    assert records == [{"amount": "12.34"}]
    # Ensure JSON encoding succeeds without relying on FastAPI's encoder.
    assert json.dumps(records) == "[{\"amount\": \"12.34\"}]"
