from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from webbed_duck import cli


def test_build_source_fingerprint_missing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "not_there"
    fingerprint = cli.build_source_fingerprint(missing)
    assert isinstance(fingerprint, cli.SourceFingerprint)
    assert dict(fingerprint.files) == {}


def test_build_source_fingerprint_detects_changes(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "demo.toml").write_text("id='demo'\n", encoding="utf-8")
    sql_path = src / "demo.sql"
    sql_path.write_text("SELECT 1;\n", encoding="utf-8")

    initial = cli.build_source_fingerprint(src)
    assert "demo.toml" in initial.files
    assert "demo.sql" in initial.files

    sql_path.write_text("SELECT 2; -- changed\n", encoding="utf-8")
    updated = cli.build_source_fingerprint(src)
    assert initial.has_changed(updated)
    assert updated.has_changed(initial)


def test_build_source_fingerprint_custom_patterns(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "include.md").write_text("docs", encoding="utf-8")

    default = cli.build_source_fingerprint(src)
    assert "include.md" not in default.files

    custom = cli.build_source_fingerprint(src, patterns=("*.md",))
    assert "include.md" in custom.files


def test_parse_param_assignments_handles_invalid_pairs() -> None:
    params = cli._parse_param_assignments(["limit=5", "flag=true"])
    assert params == {"limit": "5", "flag": "true"}

    with pytest.raises(SystemExit):
        cli._parse_param_assignments(["missing_delimiter"])


def test_parse_date_validation() -> None:
    value = cli._parse_date("2024-03-01")
    assert value == dt.date(2024, 3, 1)

    with pytest.raises(SystemExit):
        cli._parse_date("not-a-date")
