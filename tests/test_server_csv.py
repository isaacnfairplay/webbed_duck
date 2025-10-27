from __future__ import annotations

from pathlib import Path

import pytest

from webbed_duck.server.csv import append_record


def _storage_root(tmp_path: Path) -> Path:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    return storage_root


def test_append_record_rejects_absolute_destination(tmp_path: Path) -> None:
    storage_root = _storage_root(tmp_path)
    absolute = tmp_path / "elsewhere.csv"
    with pytest.raises(ValueError):
        append_record(storage_root, destination=str(absolute), columns=["a"], record={"a": 1})


def test_append_record_rejects_path_escape(tmp_path: Path) -> None:
    storage_root = _storage_root(tmp_path)
    with pytest.raises(ValueError):
        append_record(storage_root, destination="../other.csv", columns=["a"], record={"a": 1})


def test_append_record_creates_and_appends_rows(tmp_path: Path) -> None:
    storage_root = _storage_root(tmp_path)
    path = append_record(
        storage_root,
        destination="logs/events.csv",
        columns=["a", "b"],
        record={"a": 1, "b": "first"},
    )

    assert path.exists()
    contents = path.read_text(encoding="utf-8").splitlines()
    assert contents == ["a,b", "1,first"]

    append_record(
        storage_root,
        destination="logs/events.csv",
        columns=["a", "b"],
        record={"a": 2},
    )

    contents = path.read_text(encoding="utf-8").splitlines()
    assert contents == ["a,b", "1,first", "2,"]
