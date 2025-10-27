from __future__ import annotations

import datetime as dt
from pathlib import Path

import types

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


def test_start_watcher_clamps_interval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class _FakeThread:
        def start(self) -> None:  # pragma: no cover - trivial
            captured["started"] = True

    def fake_thread(*, target, args, daemon, name):  # type: ignore[no-untyped-def]
        captured["target"] = target
        captured["args"] = args
        captured["daemon"] = daemon
        captured["name"] = name
        return _FakeThread()

    monkeypatch.setattr(cli.threading, "Thread", fake_thread)

    app = types.SimpleNamespace(state=types.SimpleNamespace())
    stop_event, thread = cli._start_watcher(app, tmp_path, tmp_path, 0.05)

    assert isinstance(stop_event, cli.threading.Event)
    assert isinstance(thread, _FakeThread)
    assert captured["name"] == "webbed-duck-watch"
    assert captured["daemon"] is True
    args = captured["args"]
    assert isinstance(args, tuple) and len(args) == 5
    assert args[1] == tmp_path and args[2] == tmp_path
    assert args[3] == pytest.approx(0.2)
