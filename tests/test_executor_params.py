from pathlib import Path
import datetime as dt

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import webbed_duck.server.execution as execution_module
from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import (
    ParameterSpec,
    ParameterType,
    RouteDefinition,
    load_compiled_routes,
)
from webbed_duck.plugins.loader import PluginLoader
from webbed_duck.server.execution import RouteExecutionError, RouteExecutor


def test_parameter_spec_boolean_accepts_whitespace() -> None:
    spec = ParameterSpec(name="flag", type=ParameterType.BOOLEAN)

    assert spec.convert(" true ") is True
    assert spec.convert("\tFALSE\n") is False
    assert spec.convert(" 1 ") is True
    assert spec.convert(" 0 ") is False


def test_parameter_spec_boolean_rejects_unknown_literal() -> None:
    spec = ParameterSpec(name="flag", type=ParameterType.BOOLEAN)

    with pytest.raises(ValueError):
        spec.convert("definitely")


def test_parameter_spec_temporal_conversions() -> None:
    date_spec = ParameterSpec(name="start", type=ParameterType.DATE)
    datetime_spec = ParameterSpec(name="event", type=ParameterType.DATETIME)

    assert date_spec.convert("2024-01-02") == dt.date(2024, 1, 2)
    assert datetime_spec.convert("2024-01-02T03:04:05Z") == dt.datetime(
        2024,
        1,
        2,
        3,
        4,
        5,
        tzinfo=dt.timezone.utc,
    )

    with pytest.raises(ValueError):
        date_spec.convert("not-a-date")
    with pytest.raises(ValueError):
        datetime_spec.convert("not-a-datetime")


def _write_pair(base: Path, stem: str, toml: str, sql: str) -> None:
    (base / f"{stem}.toml").write_text(toml, encoding="utf-8")
    (base / f"{stem}.sql").write_text(sql, encoding="utf-8")


def test_executor_coerces_parameter_types_and_repeat_params(tmp_path: Path) -> None:
    source = tmp_path / "src"
    build = tmp_path / "build"
    source.mkdir()

    _write_pair(
        source,
        "param_types",
        """id = "param_types"
path = "/param_types"
cache_mode = "passthrough"

[params]
text = "VARCHAR"

[params.count]
type = "int"
required = true

[params.ratio]
type = "float"
required = true

[params.enabled]
type = "bool"
required = true

[params.tags]
type = "str"
required = false
""".strip(),
        """WITH base AS (
    SELECT
        $text AS text_value,
        $count AS count_value,
        $ratio AS ratio_value,
        $enabled AS enabled_value
),
repeat_cte AS (
    SELECT
        count_value,
        $count AS count_again,
        $enabled AS enabled_again,
        $ratio AS ratio_again,
        $text AS text_again
    FROM base
)
SELECT
    text_value,
    count_value,
    ratio_value,
    enabled_value,
    count_again,
    enabled_again,
    ratio_again,
    text_again
FROM base
JOIN repeat_cte USING (count_value)
WHERE ($enabled = enabled_again)
  AND ($count = count_again)
  AND ($ratio = ratio_again)
  AND ($text = text_again)
  AND ($tags IS NULL OR text_value IN $tags)
  AND ($tags IS NULL OR text_again IN $tags);
""".strip(),
    )

    compile_routes(source, build)
    routes = load_compiled_routes(build)
    route = next(item for item in routes if item.id == "param_types")

    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"

    executor = RouteExecutor(
        {item.id: item for item in routes},
        cache_store=None,
        config=config,
        plugin_loader=PluginLoader(config.server.plugins_dir),
    )

    incoming = {
        "text": "Alpha",
        "count": "7",
        "ratio": "2.5",
        "enabled": "TRUE",
        "tags": ["Alpha", "Omega"],
    }

    prepared = executor._prepare(route, incoming, ordered=None, preprocessed=False)

    assert prepared.params["text"] == "Alpha"
    assert prepared.params["count"] == 7
    assert prepared.params["ratio"] == pytest.approx(2.5)
    assert prepared.params["enabled"] is True
    assert prepared.params["tags"] == ["Alpha", "Omega"]

    expected_order = [
        "text",
        "count",
        "ratio",
        "enabled",
        "count",
        "enabled",
        "ratio",
        "text",
        "enabled",
        "count",
        "ratio",
        "text",
        "tags",
        "tags",
        "tags",
        "tags",
    ]
    assert list(route.param_order) == expected_order

    for name, bound in zip(route.param_order, prepared.ordered):
        if name == "ratio":
            assert bound == pytest.approx(2.5)
        elif name == "tags":
            assert bound == ["Alpha", "Omega"]
        elif name == "count":
            assert bound == 7
        elif name == "enabled":
            assert bound is True
        elif name == "text":
            assert bound == "Alpha"
        else:  # pragma: no cover - defensive safeguard
            pytest.fail(f"Unexpected parameter {name!r}")

    result = executor.execute_relation(route, incoming, offset=0, limit=None)
    table = result.table
    assert table.num_rows == 1
    data = table.to_pydict()
    assert data["text_value"] == ["Alpha"]
    assert data["count_value"] == [7]


def test_executor_renders_template_only_literal(tmp_path: Path) -> None:
    source = tmp_path / "src"
    build = tmp_path / "build"
    source.mkdir()

    _write_pair(
        source,
        "template_literal",
        """id = "template_literal"
path = "/template"
cache_mode = "passthrough"

[params]
[params.data_path]
type = "str"
template_only = true

[params.data_path.template]
policy = "literal"

[params.data_path.guard]
mode = "path"
""".strip(),
        """SELECT {{data_path}} AS rendered""",
    )

    compile_routes(source, build)
    routes = load_compiled_routes(build)
    route = next(item for item in routes if item.id == "template_literal")

    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"

    executor = RouteExecutor(
        {item.id: item for item in routes},
        cache_store=None,
        config=config,
        plugin_loader=PluginLoader(config.server.plugins_dir),
    )

    incoming = {"data_path": "reports/daily.csv"}
    prepared = executor._prepare(route, incoming, ordered=None, preprocessed=False)

    assert "data_path" not in prepared.bindings
    assert "'reports/daily.csv'" in prepared.sql

    result = executor.execute_relation(route, incoming, offset=0, limit=None)
    table = result.table.to_pydict()
    assert table["rendered"] == ["reports/daily.csv"]


def test_executor_template_path_guard_rejects_parent(tmp_path: Path) -> None:
    source = tmp_path / "src"
    build = tmp_path / "build"
    source.mkdir()

    _write_pair(
        source,
        "template_guard",
        """id = "template_guard"
path = "/template-guard"
cache_mode = "passthrough"

[params]
[params.data_path]
type = "str"
template_only = true

[params.data_path.template]
policy = "path"

[params.data_path.guard]
mode = "path"
""".strip(),
        """SELECT {{data_path | path}} AS sanitized""",
    )

    compile_routes(source, build)
    routes = load_compiled_routes(build)
    route = next(item for item in routes if item.id == "template_guard")

    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"

    executor = RouteExecutor(
        {item.id: item for item in routes},
        cache_store=None,
        config=config,
        plugin_loader=PluginLoader(config.server.plugins_dir),
    )

    with pytest.raises(RouteExecutionError):
        executor._prepare(route, {"data_path": "../secrets"}, ordered=None, preprocessed=False)


def test_executor_rejects_db_params_in_file_functions(tmp_path: Path) -> None:
    source = tmp_path / "src"
    build = tmp_path / "build"
    source.mkdir()

    _write_pair(
        source,
        "file_fn",
        """id = "file_fn"
path = "/file-fn"
cache_mode = "passthrough"

[params]
[params.path]
type = "str"
required = true
""".strip(),
        """SELECT * FROM read_parquet($path) LIMIT 1""",
    )

    compile_routes(source, build)
    routes = load_compiled_routes(build)
    route = next(item for item in routes if item.id == "file_fn")

    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"

    executor = RouteExecutor(
        {item.id: item for item in routes},
        cache_store=None,
        config=config,
        plugin_loader=PluginLoader(config.server.plugins_dir),
    )

    with pytest.raises(RouteExecutionError):
        executor._prepare(route, {"path": "data/sample.parquet"}, ordered=None, preprocessed=False)


def test_executor_allows_file_functions_when_configured(tmp_path: Path) -> None:
    source = tmp_path / "src"
    build = tmp_path / "build"
    source.mkdir()

    _write_pair(
        source,
        "file_fn_ok",
        """id = "file_fn_ok"
path = "/file-fn-ok"
cache_mode = "passthrough"

[params]
[params.path]
type = "str"
required = true
""".strip(),
        """SELECT 1 AS value WHERE LENGTH($path) > 0""",
    )

    compile_routes(source, build)
    routes = load_compiled_routes(build)
    route = next(item for item in routes if item.id == "file_fn_ok")

    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.interpolation.forbid_db_params_in_file_functions = False

    executor = RouteExecutor(
        {item.id: item for item in routes},
        cache_store=None,
        config=config,
        plugin_loader=PluginLoader(config.server.plugins_dir),
    )

    prepared = executor._prepare(route, {"path": "logs/output"}, ordered=None, preprocessed=False)
    assert "path" in prepared.bindings
    assert "$path" in prepared.sql


def test_executor_handles_temporal_params(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "src"
    build = tmp_path / "build"
    source.mkdir()

    _write_pair(
        source,
        "temporal_params",
        """id = "temporal_params"
path = "/temporal_params"
cache_mode = "passthrough"

[params.start_date]
type = "date"
required = true

[params.event_at]
type = "datetime"
required = true
""".strip(),
        """SELECT
    $start_date AS start_value,
    $event_at AS event_value,
    CAST($start_date AS DATE) AS cast_start,
    CAST($event_at AS TIMESTAMP) AS cast_event
""".strip(),
    )

    compile_routes(source, build)
    routes = load_compiled_routes(build)
    route = next(item for item in routes if item.id == "temporal_params")

    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"

    executor = RouteExecutor(
        {item.id: item for item in routes},
        cache_store=None,
        config=config,
        plugin_loader=PluginLoader(config.server.plugins_dir),
    )

    captured: dict[str, object] = {}

    def _capture(
        steps,
        params,
        *,
        route,
        request,
        loader,
    ):
        captured["params"] = dict(params)
        return dict(params)

    monkeypatch.setattr(execution_module, "run_preprocessors", _capture)

    incoming = {
        "start_date": "2024-05-06",
        "event_at": "2024-05-06T15:30:45Z",
    }

    prepared = executor._prepare(route, incoming, ordered=None, preprocessed=False)

    assert isinstance(prepared.params["start_date"], dt.date)
    assert isinstance(prepared.params["event_at"], dt.datetime)
    assert prepared.params["event_at"].tzinfo is not None

    captured_params = captured.get("params")
    assert isinstance(captured_params, dict)
    assert isinstance(captured_params["start_date"], dt.date)
    assert isinstance(captured_params["event_at"], dt.datetime)

    result = executor.execute_relation(route, incoming, offset=0, limit=None)
    table = result.table
    assert table.num_rows == 1
    data = table.to_pydict()
    assert data["cast_start"] == [dt.date(2024, 5, 6)]
    event_value = data["cast_event"][0]
    assert isinstance(event_value, dt.datetime)
    assert event_value.replace(tzinfo=None) == dt.datetime(2024, 5, 6, 15, 30, 45)

def test_constant_binding_handles_quotes(tmp_path: Path) -> None:
    source = tmp_path / "src"
    build = tmp_path / "build"
    source.mkdir()

    _write_pair(
        source,
        "quoted",
        """id = "quoted"
path = "/quoted"
cache_mode = "passthrough"

[constants]
dangerous = "O'Brian"
""".strip(),
        "SELECT {{const.dangerous}} AS value",
    )

    compile_routes(source, build)
    routes = load_compiled_routes(build)
    route = next(item for item in routes if item.id == "quoted")
    con = duckdb.connect()
    try:
        result = con.execute(route.prepared_sql, route.constant_params).fetchone()
    finally:
        con.close()
    assert result == ("O'Brian",)


def test_executor_reports_conversion_failure(tmp_path: Path) -> None:
    source = tmp_path / "src"
    build = tmp_path / "build"
    source.mkdir()

    _write_pair(
        source,
        "needs_int",
        """id = "needs_int"
path = "/needs_int"
cache_mode = "passthrough"

[params.value]
type = "int"
required = true
""".strip(),
        "SELECT $value AS coerced",  # noqa: P103 - intentional placeholder
    )

    compile_routes(source, build)
    routes = load_compiled_routes(build)
    route = next(item for item in routes if item.id == "needs_int")

    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"

    executor = RouteExecutor(
        {item.id: item for item in routes},
        cache_store=None,
        config=config,
        plugin_loader=PluginLoader(config.server.plugins_dir),
    )

    with pytest.raises(RouteExecutionError) as excinfo:
        executor.execute_relation(route, params={"value": "not-an-int"}, offset=0, limit=None)

    message = str(excinfo.value)
    assert "value" in message
    assert "Unable to convert" in message


def test_prepare_skips_preprocessors_when_marked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"

    route = RouteDefinition(
        id="pre_flagged",
        path="/pre_flagged",
        methods=["GET"],
        raw_sql="SELECT 1",
        prepared_sql="SELECT 1",
        param_order=["name"],
        params=(ParameterSpec(name="name"),),
        metadata={},
        preprocess=(
            {"callable": "tests.fake_preprocessors:add_suffix", "suffix": "-ignored"},
        ),
    )

    def _fail(*_args, **_kwargs):  # pragma: no cover - should not be invoked
        raise AssertionError("run_preprocessors should be skipped when preprocessed=True")

    monkeypatch.setattr(execution_module, "run_preprocessors", _fail)

    executor = RouteExecutor(
        {route.id: route},
        cache_store=None,
        config=config,
        plugin_loader=PluginLoader(config.server.plugins_dir),
    )
    prepared = executor._prepare(route, {"name": "duck"}, ordered=["sentinel"], preprocessed=True)

    assert prepared.params == {"name": "duck"}
    assert prepared.ordered == ["sentinel"]


def test_prepare_respects_values_added_by_preprocessors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"

    route = RouteDefinition(
        id="pre_injected",
        path="/pre_injected",
        methods=["GET"],
        raw_sql="SELECT 1",
        prepared_sql="SELECT 1",
        param_order=["cursor", "optional"],
        params=(
            ParameterSpec(name="cursor", required=False, default=None),
            ParameterSpec(name="optional", required=False, default=None),
        ),
        metadata={},
        preprocess=({"callable": "tests.fake_preprocessors:add_suffix", "suffix": ""},),
    )

    def _fake_preprocessors(steps, params, *, route, request, loader):  # type: ignore[override]
        assert steps == route.preprocess
        assert params == {"cursor": None, "optional": None}
        updated = dict(params)
        updated["cursor"] = "2024-01-01"
        updated["optional"] = "set-by-pre"
        return updated

    monkeypatch.setattr(execution_module, "run_preprocessors", _fake_preprocessors)

    executor = RouteExecutor(
        {route.id: route},
        cache_store=None,
        config=config,
        plugin_loader=PluginLoader(config.server.plugins_dir),
    )
    prepared = executor._prepare(route, {}, ordered=None, preprocessed=False)

    assert prepared.params["cursor"] == "2024-01-01"
    assert prepared.params["optional"] == "set-by-pre"
    assert prepared.ordered == ["2024-01-01", "set-by-pre"]


def test_executor_executes_duckdb_table_function_file_bindings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.interpolation.forbid_db_params_in_file_functions = False

    data_single = pa.table({"value": pa.array([1], type=pa.int64())})
    data_multi = pa.table({"value": pa.array([2, 3], type=pa.int64())})
    single_path = tmp_path / "single.parquet"
    second_path = tmp_path / "second.parquet"
    pq.write_table(data_single, single_path)
    pq.write_table(data_multi, second_path)

    source = tmp_path / "src"
    build = tmp_path / "build"
    source.mkdir()

    _write_pair(
        source,
        "duckdb_paths",
        """id = "duckdb_paths"
path = "/duckdb_paths"
cache_mode = "passthrough"

[params.single_path]
type = "str"
required = true

[params.multi_paths]
type = "str"
required = false
""".strip(),
        """WITH single_source AS (
    SELECT COUNT(*) AS single_count, SUM(value) AS single_sum
    FROM read_parquet($single_path::TEXT)
),
multi_source AS (
    SELECT COUNT(*) AS multi_count, SUM(value) AS multi_sum
    FROM read_parquet($multi_paths::TEXT[])
)
SELECT
    single_source.single_count,
    single_source.single_sum,
    multi_source.multi_count,
    multi_source.multi_sum
FROM single_source
CROSS JOIN multi_source;
""".strip(),
    )

    compile_routes(source, build)
    routes = load_compiled_routes(build)
    route = next(item for item in routes if item.id == "duckdb_paths")

    def _inject_file_list(steps, params, *, route, request, loader):  # type: ignore[override]
        assert steps == route.preprocess
        assert params["single_path"] == str(single_path)
        assert params.get("multi_paths") is None
        updated = dict(params)
        updated["multi_paths"] = [str(single_path), str(second_path)]
        return updated

    monkeypatch.setattr(execution_module, "run_preprocessors", _inject_file_list)

    executor = RouteExecutor(
        {route.id: route},
        cache_store=None,
        config=config,
        plugin_loader=PluginLoader(config.server.plugins_dir),
    )
    prepared = executor._prepare(
        route,
        {"single_path": str(single_path)},
        ordered=None,
        preprocessed=False,
    )

    assert prepared.params["single_path"] == str(single_path)
    assert prepared.params["multi_paths"] == [str(single_path), str(second_path)]
    assert prepared.ordered == [str(single_path), [str(single_path), str(second_path)]]

    result = executor.execute_relation(
        route,
        params={"single_path": str(single_path)},
        offset=0,
        limit=None,
    )

    table = result.table
    assert table.num_rows == 1
    data = table.to_pydict()
    assert data["single_count"] == [1]
    assert data["single_sum"] == [1]
    assert data["multi_count"] == [3]
    assert data["multi_sum"] == [6]

def test_executor_allows_template_paths_in_file_functions(tmp_path: Path) -> None:
    source = tmp_path / "src"
    build = tmp_path / "build"
    source.mkdir()

    _write_pair(
        source,
        "file_fn_template",
        """id = "file_fn_template"
path = "/file-fn-template"
cache_mode = "passthrough"

[params]
[params.data_path]
type = "str"
template_only = true

[params.data_path.template]
policy = "path"
""".strip(),
        """SELECT * FROM read_parquet({{ data_path | path }}) LIMIT 5""",
    )

    compile_routes(source, build)
    routes = load_compiled_routes(build)
    route = next(item for item in routes if item.id == "file_fn_template")

    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"

    executor = RouteExecutor(
        {item.id: item for item in routes},
        cache_store=None,
        config=config,
        plugin_loader=PluginLoader(config.server.plugins_dir),
    )

    prepared = executor._prepare(
        route,
        {"data_path": "datasets/logs/2024.parquet"},
        ordered=None,
        preprocessed=False,
    )

    assert "data_path" not in prepared.bindings
    assert "read_parquet" in prepared.sql
    assert "$" not in prepared.sql
