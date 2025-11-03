"""Extensive CLI and developer tooling test matrix.

Timeline
--------
T0  Map command dispatch behaviours.
T1  Exercise performance reporting helpers.
T2  Validate parameter and date parsing across edge cases.
T3  Capture watcher fingerprint semantics without runtime side effects.

These tests focus exclusively on CLI-facing utilities to broaden
regression coverage without modifying the application runtime.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from webbed_duck import cli


PERF_CASES = [
    ([1.0], 100, 1.0, 1.0),
    ([1.0, 2.0], 42, 1.5, 2.0),
    ([5.5, 6.5, 7.5], 3, 6.5, 7.5),
    ([10.0, 20.0, 30.0, 40.0], 12, 25.0, 40.0),
    ([0.5, 0.75, 1.0, 1.25, 1.5], 5, 1.0, 1.5),
    ([100.0, 80.0, 60.0, 40.0], 1, 70.0, 100.0),
    ([3.3, 3.3, 3.3, 3.3], 7, 3.3, 3.3),
    ([0.01, 0.02, 0.03], 2, 0.02, 0.03),
    ([15.2, 14.9, 15.5, 15.0, 15.4, 15.1], 64, 15.183333333333334, 15.5),
    ([2.5, 2.1, 2.2, 2.3, 2.4, 2.6, 2.7, 2.8], 9, 2.45, 2.8),
]


@pytest.mark.parametrize(
    ("timings", "rows", "expected_avg", "expected_p95"),
    PERF_CASES,
    ids=[f"perf-{index}" for index, _ in enumerate(PERF_CASES, start=1)],
)
def test_perfstats_from_timings(timings: Sequence[float], rows: int, expected_avg: Any, expected_p95: Any) -> None:
    """Ensure ``PerfStats.from_timings`` summarises latency metrics correctly."""

    stats = cli.PerfStats.from_timings(timings, rows)
    assert stats.iterations == len(timings)
    assert stats.rows_returned == rows
    assert stats.average_ms == pytest.approx(expected_avg)
    assert stats.p95_ms == pytest.approx(expected_p95)


REPORT_CASES = [
    ("route.one", cli.PerfStats(iterations=5, rows_returned=10, average_ms=12.345, p95_ms=20.0)),
    ("route.two", cli.PerfStats(iterations=1, rows_returned=0, average_ms=1.0, p95_ms=1.0)),
    ("analytics.dashboard", cli.PerfStats(iterations=15, rows_returned=1200, average_ms=45.5, p95_ms=75.25)),
    ("delta.update", cli.PerfStats(iterations=7, rows_returned=32, average_ms=6.789, p95_ms=7.654)),
    ("report.monthly", cli.PerfStats(iterations=9, rows_returned=256, average_ms=123.0, p95_ms=150.0)),
]


@pytest.mark.parametrize(
    ("route_id", "stats"),
    REPORT_CASES,
    ids=[name for name, _ in REPORT_CASES],
)
def test_perfstats_format_report(route_id: str, stats: cli.PerfStats) -> None:
    """Verify the formatted performance report contains all summary fields."""

    report = stats.format_report(route_id)
    for fragment in (
        f"Route: {route_id}",
        f"Iterations: {stats.iterations}",
        f"Rows (last run): {stats.rows_returned}",
        "Average latency:",
        "95th percentile latency:",
    ):
        assert fragment in report


FINGERPRINT_CASES = [
    ({"a.sql": (1.0, 100)}, {"a.sql": (1.0, 100)}, False),
    ({"a.sql": (1.0, 100)}, {"a.sql": (2.0, 100)}, True),
    ({"a.sql": (1.0, 100)}, {"a.sql": (1.0, 200)}, True),
    ({"a.sql": (1.0, 100)}, {"a.sql": (1.0, 100), "b.sql": (1.0, 50)}, True),
    ({"a.sql": (1.0, 100), "b.sql": (2.0, 200)}, {"b.sql": (2.0, 200)}, True),
    ({"nested/c.md": (3.0, 300)}, {"nested/c.md": (3.0, 300)}, False),
]


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    FINGERPRINT_CASES,
    ids=[f"fingerprint-{index}" for index, _ in enumerate(FINGERPRINT_CASES, start=1)],
)
def test_source_fingerprint_has_changed(left: Mapping[str, tuple[float, int]], right: Mapping[str, tuple[float, int]], expected: bool) -> None:
    """Confirm file fingerprints detect any metadata drift."""

    assert cli.SourceFingerprint(left).has_changed(cli.SourceFingerprint(right)) is expected


PARAM_ASSIGNMENT_CASES = [
    (["limit=10"], {"limit": "10"}),
    (["limit=10", "order=desc"], {"limit": "10", "order": "desc"}),
    (["alpha=beta=gamma"], {"alpha": "beta=gamma"}),
    (["flag=true", "path=/tmp/data"], {"flag": "true", "path": "/tmp/data"}),
    (["spaces=value with spaces"], {"spaces": "value with spaces"}),
]


@pytest.mark.parametrize(
    ("pairs", "expected"),
    PARAM_ASSIGNMENT_CASES,
    ids=[f"params-{index}" for index, _ in enumerate(PARAM_ASSIGNMENT_CASES, start=1)],
)
def test_parse_param_assignments_matrix(pairs: Sequence[str], expected: Mapping[str, str]) -> None:
    """Stress ``_parse_param_assignments`` with varied key/value structures."""

    assert cli._parse_param_assignments(pairs) == expected


INVALID_PARAM_CASES = [
    ["missing"],
    ["spaces not-equals"],
    ["invalid", "name=value"],
]


@pytest.mark.parametrize(
    "pairs",
    INVALID_PARAM_CASES,
    ids=[f"params-invalid-{index}" for index, _ in enumerate(INVALID_PARAM_CASES, start=1)],
)
def test_parse_param_assignments_invalid(pairs: Sequence[str]) -> None:
    """Invalid ``name=value`` pairs should raise ``SystemExit`` for CLI parity."""

    with pytest.raises(SystemExit):
        cli._parse_param_assignments(pairs)


VALID_DATES = [
    "2024-01-01",
    "1999-12-31",
    "2030-06-15",
    "2025-02-28",
]


@pytest.mark.parametrize("value", VALID_DATES, ids=[f"date-{value}" for value in VALID_DATES])
def test_parse_date_valid(value: str) -> None:
    """Ensure ISO-8601 dates are accepted by ``_parse_date``."""

    parsed = cli._parse_date(value)
    assert isinstance(parsed, datetime.date)
    assert parsed.isoformat() == value


INVALID_DATES = ["2024-13-01", "not-a-date"]


@pytest.mark.parametrize("value", INVALID_DATES, ids=[f"date-invalid-{value}" for value in INVALID_DATES])
def test_parse_date_invalid(value: str) -> None:
    """Reject malformed date strings with a ``SystemExit`` for user feedback."""

    with pytest.raises(SystemExit):
        cli._parse_date(value)


COMMAND_CASES = [
    ("compile", ["compile", "--source", "src", "--build", "out"], {"source": "src", "build": "out"}),
    ("serve", ["serve", "--build", "build", "--host", "0.0.0.0", "--port", "9000"], {"host": "0.0.0.0", "port": 9000}),
    ("run-incremental", ["run-incremental", "route.id", "--param", "cursor", "--start", "2024-01-01", "--end", "2024-01-31"], {"route_id": "route.id", "param": "cursor"}),
    ("perf", ["perf", "route.id", "--iterations", "2"], {"route_id": "route.id", "iterations": 2}),
    ("unknown", ["unknown"], {}),
]


@pytest.mark.parametrize(
    ("command", "argv", "expect"),
    COMMAND_CASES,
    ids=[name for name, *_ in COMMAND_CASES],
)
def test_main_dispatch_matrix(monkeypatch: pytest.MonkeyPatch, command: str, argv: Sequence[str], expect: Mapping[str, Any]) -> None:
    """Exercise CLI command dispatch paths without invoking heavy side effects."""

    calls: list[dict[str, Any]] = []

    def record(name: str):
        def _impl(*args, **kwargs):
            payload = {"name": name, "args": args, "kwargs": kwargs}
            if args:
                namespace = args[0]
                if hasattr(namespace, "__dict__"):
                    payload["namespace"] = namespace.__dict__.copy()
            calls.append(payload)
            return 0

        return _impl

    monkeypatch.setattr(cli, "_cmd_compile", record("compile"))
    monkeypatch.setattr(cli, "_cmd_serve", record("serve"))
    monkeypatch.setattr(cli, "_cmd_run_incremental", record("run-incremental"))
    monkeypatch.setattr(cli, "_cmd_perf", record("perf"))

    if command == "unknown":
        with pytest.raises(SystemExit) as exc:
            cli.main(argv)
        assert exc.value.code == 2
        assert not calls
        return

    exit_code = cli.main(argv)

    assert exit_code == 0
    expected_name = "run-incremental" if command == "run-incremental" else command
    assert calls[-1]["name"] == expected_name
    namespace = calls[-1].get("namespace", {})
    for key, value in expect.items():
        if key in namespace:
            assert namespace[key] == value
        else:
            assert value in calls[-1]["args"]


COMPILE_AND_RELOAD_CASES = [
    (
        "default-loader",
        ["route.one", "route.two"],
    ),
    (
        "single-route",
        ["analytics.dashboard"],
    ),
]


@pytest.mark.parametrize("label", [case[0] for case in COMPILE_AND_RELOAD_CASES])
def test_compile_and_reload_invokes_reload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, label: str) -> None:
    """Simulate the watcher reload path with deterministic compile/load outcomes."""

    routes = next(routes for name, routes in COMPILE_AND_RELOAD_CASES if name == label)
    captured: dict[str, Any] = {}

    def fake_compile(source: Path, build: Path) -> None:
        captured["compiled"] = (source, build)

    def fake_load(path: Path) -> list[str]:
        captured["loaded"] = path
        return routes

    class State:
        def __init__(self) -> None:
            self.last = None

        def reload_routes(self, payload: Any) -> None:
            self.last = payload

    class App:
        def __init__(self) -> None:
            self.state = State()

    app = App()
    source_dir = tmp_path / "src"
    build_dir = tmp_path / "build"

    result = cli._compile_and_reload(app, source_dir, build_dir, compile_fn=fake_compile, load_fn=fake_load)
    assert captured["compiled"] == (source_dir, build_dir)
    assert captured["loaded"] == build_dir
    assert app.state.last == routes
    assert result == len(routes)


def test_compile_and_reload_missing_reload_handler(tmp_path: Path) -> None:
    """If an app lacks ``reload_routes`` the helper should fail fast."""

    class EmptyApp:
        def __init__(self) -> None:
            self.state = object()

    with pytest.raises(RuntimeError):
        cli._compile_and_reload(EmptyApp(), tmp_path / "src", tmp_path / "build", compile_fn=lambda *_: None, load_fn=lambda _: [])
