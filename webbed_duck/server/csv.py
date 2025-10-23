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

    The file is created with a header row when it does not yet exist. A
    ``ValueError`` is raised when ``destination`` is absolute or escapes the
    ``runtime/appends`` directory relative to ``storage_root``.
    """

    appends_dir = Path(storage_root) / "runtime" / "appends"
    appends_dir.mkdir(parents=True, exist_ok=True)

    destination_path = Path(destination)
    if destination_path.is_absolute():
        raise ValueError("Append destination must be a relative path")

    resolved_appends_dir = appends_dir.resolve()
    path = (appends_dir / destination_path).resolve(strict=False)

    try:
        path.relative_to(resolved_appends_dir)
    except ValueError as exc:
        raise ValueError("Append destination must stay within runtime/appends") from exc

    path.parent.mkdir(parents=True, exist_ok=True)

    is_new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        if is_new:
            writer.writeheader()
        writer.writerow({column: record.get(column) for column in columns})
    return path


__all__ = ["append_record"]
