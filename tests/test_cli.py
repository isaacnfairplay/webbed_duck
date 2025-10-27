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


def test_perf_stats_from_timings() -> None:
    stats = cli.PerfStats.from_timings([3.0, 1.0, 2.0], rows_returned=5)
    assert stats.iterations == 3
    assert stats.rows_returned == 5
    assert stats.average_ms == pytest.approx(2.0)
    assert stats.p95_ms == pytest.approx(3.0)

    report = stats.format_report("demo")
    assert "Route: demo" in report
    assert "Iterations: 3" in report

    with pytest.raises(ValueError):
        cli.PerfStats.from_timings([], rows_returned=0)


def test_cmd_perf_reports_stats(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = types.SimpleNamespace(route_id="demo", build="build", config="config.toml", iterations=2, param=["limit=5"])
    config_obj = object()
    monkeypatch.setattr(cli, "load_config", lambda path: config_obj)

    tables = [types.SimpleNamespace(num_rows=1), types.SimpleNamespace(num_rows=4)]

    def fake_run_route(route_id, params, build_dir, config, format):  # type: ignore[no-untyped-def]
        assert route_id == "demo"
        assert params == {"limit": "5"}
        assert build_dir == "build"
        assert config is config_obj
        assert format == "table"
        return tables.pop(0)

    monkeypatch.setattr(cli, "run_route", fake_run_route)

    perf_calls = iter([0.0, 0.001, 1.0, 1.004])
    monkeypatch.setattr(cli.time, "perf_counter", lambda: next(perf_calls))

    code = cli._cmd_perf(args)
    assert code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "Route: demo"
    assert "Iterations: 2" in lines[1]
    assert any("Average latency" in line for line in lines)
    assert any("Rows (last run): 4" in line for line in lines)


def test_compile_and_reload_invokes_reload(tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def fake_compile(source_dir: Path, build_dir: Path) -> None:
        called["compile"] = (source_dir, build_dir)

    def fake_load(build_dir: Path) -> list[str]:
        called["load"] = build_dir
        return ["a", "b"]

    captured: dict[str, object] = {}
    app = types.SimpleNamespace(state=types.SimpleNamespace(reload_routes=lambda routes: captured.setdefault("routes", routes)))

    count = cli._compile_and_reload(app, tmp_path, tmp_path / "build", compile_fn=fake_compile, load_fn=fake_load)
    assert count == 2
    assert called["compile"] == (tmp_path, tmp_path / "build")
    assert called["load"] == tmp_path / "build"
    assert captured["routes"] == ["a", "b"]


def test_compile_and_reload_requires_reload(tmp_path: Path) -> None:
    app = types.SimpleNamespace(state=types.SimpleNamespace())

    with pytest.raises(RuntimeError):
        cli._compile_and_reload(
            app,
            tmp_path,
            tmp_path / "build",
            compile_fn=lambda *_args, **_kwargs: None,
            load_fn=lambda _build: [],
        )
