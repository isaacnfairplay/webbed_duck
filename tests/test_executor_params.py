from pathlib import Path

import pytest

from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.execution import RouteExecutionError, RouteExecutor


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

    executor = RouteExecutor({item.id: item for item in routes}, cache_store=None, config=config)

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
    assert data["ratio_value"][0] == pytest.approx(2.5)
    assert data["enabled_value"] == [True]
    assert data["count_again"] == [7]
    assert data["enabled_again"] == [True]
    assert data["ratio_again"][0] == pytest.approx(2.5)
    assert data["text_again"] == ["Alpha"]


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

    executor = RouteExecutor({item.id: item for item in routes}, cache_store=None, config=config)

    with pytest.raises(RouteExecutionError) as excinfo:
        executor.execute_relation(route, params={"value": "not-an-int"}, offset=0, limit=None)

    message = str(excinfo.value)
    assert "value" in message
    assert "Unable to convert" in message
