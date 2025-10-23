from __future__ import annotations

import csv
from pathlib import Path
from typing import Mapping, Sequence


def append_record(
    storage_root: Path,
    *,
    destination: str,
    columns: Sequence[str],
    record: Mapping[str, object],
) -> Path:
    """Append ``record`` to a CSV file under ``storage_root``.

    The file is created with a header row when it does not yet exist.
    """

    appends_dir = Path(storage_root) / "runtime" / "appends"
    appends_dir.mkdir(parents=True, exist_ok=True)
    path = appends_dir / destination
    is_new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        if is_new:
            writer.writeheader()
        writer.writerow({column: record.get(column) for column in columns})
    return path


__all__ = ["append_record"]
