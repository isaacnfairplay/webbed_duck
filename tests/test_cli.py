from __future__ import annotations

import datetime as dt
from pathlib import Path

import sys
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
    assert "include.md" in default.files

    custom = cli.build_source_fingerprint(src, patterns=("*.md",))
    assert set(custom.files) == {"include.md"}


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


def test_start_watcher_clamps_interval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
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
    out = capsys.readouterr().out
    assert "[webbed-duck] Watching" in out
    assert "interval=0.20s" in out


def test_watch_iteration_skips_when_fingerprint_unchanged(tmp_path: Path) -> None:
    src = tmp_path / "src"
    build = tmp_path / "build"
    src.mkdir()
    build.mkdir()
    (src / "demo.toml").write_text("id='demo'\n", encoding="utf-8")
    (src / "demo.sql").write_text("SELECT 1;\n", encoding="utf-8")

    snapshot = cli.build_source_fingerprint(src)
    app = object()
    called: dict[str, object] = {}

    def fake_reload(app_arg, source_dir, build_dir):  # type: ignore[no-untyped-def]
        called["app"] = app_arg
        return 5

    updated, count = cli._watch_iteration(
        app,
        src,
        build,
        snapshot,
        compile_and_reload=fake_reload,
    )

    assert count == 0
    assert updated is snapshot
    assert called == {}


def test_watch_iteration_triggers_reload_on_change(tmp_path: Path) -> None:
    src = tmp_path / "src"
    build = tmp_path / "build"
    src.mkdir()
    build.mkdir()
    toml_path = src / "demo.toml"
    sql_path = src / "demo.sql"
    toml_path.write_text("id='demo'\n", encoding="utf-8")
    sql_path.write_text("SELECT 1;\n", encoding="utf-8")

    snapshot = cli.build_source_fingerprint(src)
    sql_path.write_text("SELECT 2; -- change\n", encoding="utf-8")

    app = object()
    calls: dict[str, object] = {}

    def fake_reload(app_arg, source_dir, build_dir):  # type: ignore[no-untyped-def]
        calls["app"] = app_arg
        calls["source"] = source_dir
        calls["build"] = build_dir
        return 2

    updated, count = cli._watch_iteration(
        app,
        src,
        build,
        snapshot,
        compile_and_reload=fake_reload,
    )

    assert count == 2
    assert updated.has_changed(snapshot)
    assert calls == {"app": app, "source": src, "build": build}


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


def test_cmd_compile_reports_count(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    captured: dict[str, object] = {}

    def fake_compile(source: str | Path, build: str | Path) -> list[str]:
        captured["source"] = source
        captured["build"] = build
        return ["a", "b", "c"]

    monkeypatch.setattr(cli, "compile_routes", fake_compile)

    code = cli._cmd_compile("src", "build")
    assert code == 0
    assert captured == {"source": "src", "build": "build"}
    out = capsys.readouterr().out.strip()
    assert out == "Compiled 3 route(s) to build"


def test_cmd_run_incremental_invokes_runner(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    args = types.SimpleNamespace(
        route_id="demo",
        param="cursor",
        start="2024-01-01",
        end="2024-01-03",
        build="build",
        config="config.toml",
    )
    config_obj = object()
    monkeypatch.setattr(cli, "load_config", lambda path: config_obj)

    captured: dict[str, object] = {}
    results = [
        types.SimpleNamespace(route_id="demo", cursor_param="cursor", value="2024-01-01", rows_returned=5),
        types.SimpleNamespace(route_id="demo", cursor_param="cursor", value="2024-01-02", rows_returned=7),
    ]

    def fake_run_incremental(
        route_id: str,
        *,
        cursor_param: str,
        start: dt.date,
        end: dt.date,
        config,
        build_dir,
    ):
        captured["route_id"] = route_id
        captured["cursor_param"] = cursor_param
        captured["start"] = start
        captured["end"] = end
        captured["config"] = config
        captured["build_dir"] = build_dir
        return results

    monkeypatch.setattr(cli, "run_incremental", fake_run_incremental)

    code = cli._cmd_run_incremental(args)
    assert code == 0
    assert captured == {
        "route_id": "demo",
        "cursor_param": "cursor",
        "start": dt.date(2024, 1, 1),
        "end": dt.date(2024, 1, 3),
        "config": config_obj,
        "build_dir": "build",
    }
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines == [
        "demo cursor=2024-01-01 rows=5",
        "demo cursor=2024-01-02 rows=7",
    ]


def test_cmd_serve_auto_compile_and_watch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    build_dir = tmp_path / "build"
    build_dir.mkdir()

    server_config = types.SimpleNamespace(
        build_dir=build_dir,
        source_dir=None,
        auto_compile=False,
        watch=False,
        watch_interval=1.5,
        host="127.0.0.1",
        port=8000,
    )
    config_obj = types.SimpleNamespace(server=server_config)

    monkeypatch.setattr(cli, "load_config", lambda path: config_obj)

    compiled_routes: list[Path] = []

    def fake_compile(source: Path, build: Path) -> list[str]:
        compiled_routes.append(source)
        assert build == build_dir
        return ["route"]

    monkeypatch.setattr(cli, "compile_routes", fake_compile)

    def fake_load(build: Path) -> list[str]:
        assert build == build_dir
        return ["route"]

    monkeypatch.setattr("webbed_duck.core.routes.load_compiled_routes", fake_load)

    watcher_calls: dict[str, object] = {}

    class _Stop:
        def __init__(self) -> None:
            self.set_called = False

        def set(self) -> None:
            self.set_called = True

    class _Thread:
        def __init__(self) -> None:
            self.join_timeout: float | None = None

        def join(self, timeout: float | None = None) -> None:
            self.join_timeout = timeout

    def fake_start_watcher(app, source: Path, build: Path, interval: float):  # type: ignore[no-untyped-def]
        watcher_calls["app"] = app
        watcher_calls["source"] = source
        watcher_calls["build"] = build
        watcher_calls["interval"] = interval
        stop = _Stop()
        thread = _Thread()
        watcher_calls["stop"] = stop
        watcher_calls["thread"] = thread
        return stop, thread

    monkeypatch.setattr(cli, "_start_watcher", fake_start_watcher)

    app_obj = types.SimpleNamespace()
    monkeypatch.setattr("webbed_duck.server.app.create_app", lambda routes, config: app_obj)

    run_calls: dict[str, object] = {}

    class _FakeUvicorn:
        @staticmethod
        def run(app, host: str, port: int) -> None:  # type: ignore[no-untyped-def]
            run_calls["app"] = app
            run_calls["host"] = host
            run_calls["port"] = port

    monkeypatch.setitem(sys.modules, "uvicorn", _FakeUvicorn)

    args = types.SimpleNamespace(
        build=None,
        source=str(source_dir),
        config="config.toml",
        host=None,
        port=None,
        no_auto_compile=False,
        watch=True,
        no_watch=False,
        watch_interval=None,
    )

    code = cli._cmd_serve(args)
    assert code == 0
    assert compiled_routes == [source_dir]
    assert watcher_calls["source"] == source_dir
    assert watcher_calls["build"] == build_dir
    assert watcher_calls["interval"] == 1.5
    assert watcher_calls["stop"].set_called is True
    assert watcher_calls["thread"].join_timeout == 2
    assert run_calls == {"app": app_obj, "host": "127.0.0.1", "port": 8000}
    err = capsys.readouterr().err
    assert "Auto-compile" not in err


def test_cmd_serve_watch_interval_clamp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    build_dir = tmp_path / "build"
    build_dir.mkdir()

    server_config = types.SimpleNamespace(
        build_dir=build_dir,
        source_dir=source_dir,
        auto_compile=False,
        watch=True,
        watch_interval=1.0,
        host="127.0.0.1",
        port=8000,
    )
    config_obj = types.SimpleNamespace(server=server_config)

    monkeypatch.setattr(cli, "load_config", lambda path: config_obj)
    monkeypatch.setattr(cli, "compile_routes", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "webbed_duck.core.routes.load_compiled_routes", lambda build: ["route"]
    )

    recorded: dict[str, object] = {}

    class _Stop:
        def __init__(self) -> None:
            self.called = False

        def set(self) -> None:
            self.called = True

    class _Thread:
        def __init__(self) -> None:
            self.join_timeout: float | None = None

        def join(self, timeout: float | None = None) -> None:
            self.join_timeout = timeout

    def fake_start_watcher(app, source: Path, build: Path, interval: float):  # type: ignore[no-untyped-def]
        recorded["interval"] = interval
        stop = _Stop()
        thread = _Thread()
        recorded["stop"] = stop
        recorded["thread"] = thread
        return stop, thread

    monkeypatch.setattr(cli, "_start_watcher", fake_start_watcher)

    app_obj = types.SimpleNamespace()
    monkeypatch.setattr("webbed_duck.server.app.create_app", lambda routes, config: app_obj)

    class _FakeUvicorn:
        @staticmethod
        def run(app, host: str, port: int) -> None:  # type: ignore[no-untyped-def]
            recorded["host"] = host
            recorded["port"] = port

    monkeypatch.setitem(sys.modules, "uvicorn", _FakeUvicorn)

    args = types.SimpleNamespace(
        build=None,
        source=None,
        config="config.toml",
        host=None,
        port=None,
        no_auto_compile=False,
        watch=False,
        no_watch=False,
        watch_interval=0.05,
    )

    code = cli._cmd_serve(args)
    assert code == 0
    assert recorded["interval"] == pytest.approx(cli.WATCH_INTERVAL_MIN)
    assert recorded["stop"].called is True
    assert recorded["thread"].join_timeout == 2


def test_cmd_serve_config_watch_interval_clamped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    build_dir = tmp_path / "build"
    build_dir.mkdir()

    server_config = types.SimpleNamespace(
        build_dir=build_dir,
        source_dir=source_dir,
        auto_compile=False,
        watch=True,
        watch_interval=0.05,
        host="127.0.0.1",
        port=8000,
    )
    config_obj = types.SimpleNamespace(server=server_config)

    monkeypatch.setattr(cli, "load_config", lambda path: config_obj)
    monkeypatch.setattr(cli, "compile_routes", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "webbed_duck.core.routes.load_compiled_routes", lambda build: ["route"]
    )

    recorded: dict[str, object] = {}

    class _Stop:
        def __init__(self) -> None:
            self.called = False

        def set(self) -> None:
            self.called = True

    class _Thread:
        def __init__(self) -> None:
            self.join_timeout: float | None = None

        def join(self, timeout: float | None = None) -> None:
            self.join_timeout = timeout

    def fake_start_watcher(app, source: Path, build: Path, interval: float):  # type: ignore[no-untyped-def]
        recorded["interval"] = interval
        stop = _Stop()
        thread = _Thread()
        recorded["stop"] = stop
        recorded["thread"] = thread
        return stop, thread

    monkeypatch.setattr(cli, "_start_watcher", fake_start_watcher)

    app_obj = types.SimpleNamespace()
    monkeypatch.setattr("webbed_duck.server.app.create_app", lambda routes, config: app_obj)

    class _FakeUvicorn:
        @staticmethod
        def run(app, host: str, port: int) -> None:  # type: ignore[no-untyped-def]
            recorded["host"] = host
            recorded["port"] = port

    monkeypatch.setitem(sys.modules, "uvicorn", _FakeUvicorn)

    args = types.SimpleNamespace(
        build=None,
        source=None,
        config="config.toml",
        host=None,
        port=None,
        no_auto_compile=False,
        watch=False,
        no_watch=False,
        watch_interval=None,
    )

    code = cli._cmd_serve(args)
    assert code == 0
    assert recorded["interval"] == pytest.approx(cli.WATCH_INTERVAL_MIN)
    assert recorded["stop"].called is True
    assert recorded["thread"].join_timeout == 2

def test_cmd_serve_auto_compile_failure_reports_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    build_dir = tmp_path / "build"
    build_dir.mkdir()

    server_config = types.SimpleNamespace(
        build_dir=build_dir,
        source_dir=source_dir,
        auto_compile=True,
        watch=False,
        watch_interval=1.0,
        host="127.0.0.1",
        port=8000,
    )
    config_obj = types.SimpleNamespace(server=server_config)

    monkeypatch.setattr(cli, "load_config", lambda path: config_obj)

    def failing_compile(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "compile_routes", failing_compile)

    args = types.SimpleNamespace(
        build=None,
        source=str(source_dir),
        config="config.toml",
        host=None,
        port=None,
        no_auto_compile=False,
        watch=False,
        no_watch=False,
        watch_interval=None,
    )

    code = cli._cmd_serve(args)
    assert code == 1
    err = capsys.readouterr().err
    assert "[webbed-duck] Auto-compile failed: boom" in err
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
