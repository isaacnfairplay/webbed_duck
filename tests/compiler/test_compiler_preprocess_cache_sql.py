"""Tests for preprocess, cache, and SQL helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

try:  # pragma: no cover - optional dependency in CI environments
    from hypothesis import given
    from hypothesis import strategies as st
except ModuleNotFoundError:  # pragma: no cover - executed when hypothesis missing
    pytest.skip("hypothesis not installed", allow_module_level=True)

from webbed_duck.core.compiler import (
    RouteDirective,
    RouteCompilationError,
    _build_cache,
    _normalize_preprocess_entries,
    _prepare_sql,
)
from webbed_duck.core.routes import ParameterSpec, ParameterType
from webbed_duck.plugins.loader import PluginLoader


@pytest.mark.parametrize(
    "input_data, expected",
    [
        (
            {"callable_path": "fake_preprocessors.py", "callable_name": "add_prefix", "prefix": "pre-"},
            [
                {
                    "callable_path": "fake_preprocessors.py",
                    "callable_name": "add_prefix",
                    "kwargs": {"prefix": "pre-"},
                }
            ],
        ),
        (
            [
                {
                    "callable_path": "fake_preprocessors.py",
                    "callable_name": "return_none",
                },
                {
                    "callable_path": "fake_preprocessors.py",
                    "callable_name": "add_suffix",
                    "note": "value",
                },
            ],
            [
                {
                    "callable_path": "fake_preprocessors.py",
                    "callable_name": "return_none",
                },
                {
                    "callable_path": "fake_preprocessors.py",
                    "callable_name": "add_suffix",
                    "kwargs": {"note": "value"},
                },
            ],
        ),
    ],
)
def test_normalize_preprocess_entries_success(
    plugins_dir: Path, input_data, expected
) -> None:
    source = Path(__file__).resolve().parents[1] / "fake_preprocessors.py"
    (plugins_dir / "fake_preprocessors.py").write_text(source.read_text())
    loader = PluginLoader(plugins_dir)
    assert _normalize_preprocess_entries(input_data, loader=loader) == expected


@pytest.mark.parametrize(
    "bad_input",
    [
        {"callable_name": "add_prefix"},
        {"callable_path": "fake_preprocessors.py"},
        {"callable_path": "fake_preprocessors.py", "callable_name": "missing", "kwargs": []},
        {"callable_module": "tests.fake_preprocessors", "callable_name": "add_prefix"},
    ],
)
def test_normalize_preprocess_entries_rejects_missing_callable(
    plugins_dir: Path, bad_input
) -> None:
    source = Path(__file__).resolve().parents[1] / "fake_preprocessors.py"
    (plugins_dir / "fake_preprocessors.py").write_text(source.read_text())
    loader = PluginLoader(plugins_dir)
    with pytest.raises(RouteCompilationError):
        _normalize_preprocess_entries(bad_input, loader=loader)


@st.composite
def preprocess_strategy(draw) -> Any:
    function_name = draw(st.sampled_from(["add_prefix", "add_suffix", "return_none"]))
    entry = {
        "callable_path": "fake_preprocessors.py",
        "callable_name": function_name,
    }
    if draw(st.booleans()):
        extra_kwargs = draw(
            st.dictionaries(
                keys=st.text(min_size=1, max_size=5),
                values=st.one_of(
                    st.integers(-3, 3), st.text(min_size=0, max_size=5), st.booleans()
                ),
                max_size=2,
            )
        )
        entry["kwargs"] = extra_kwargs
    if draw(st.booleans()):
        return entry
    return [entry]


@given(st.lists(preprocess_strategy(), max_size=4))
def test_normalize_preprocess_entries_property(plugins_dir: Path, chunks):
    source = Path(__file__).resolve().parents[1] / "fake_preprocessors.py"
    (plugins_dir / "fake_preprocessors.py").write_text(source.read_text())
    loader = PluginLoader(plugins_dir)
    flattened: list[dict[str, object]] = []
    for chunk in chunks:
        flattened.extend(_normalize_preprocess_entries(chunk, loader=loader))
    assert all(entry["callable_path"] == "fake_preprocessors.py" for entry in flattened)
    assert all("callable_name" in entry for entry in flattened)
    assert all(
        "kwargs" not in entry or isinstance(entry["kwargs"], dict) for entry in flattened
    )


@pytest.mark.parametrize(
    "metadata, directives, expected",
    [
        (
            {"cache": {"order_by": ["id"], "rows_per_page": 10}},
            [],
            {"order_by": ["id"], "rows_per_page": 10},
        ),
        (
            {"cache": {"order-by": "id"}},
            [RouteDirective(name="cache", args={}, value="profile-a")],
            {"order_by": ["id"], "profile": "profile-a"},
        ),
        (
            {},
            [
                RouteDirective(
                    name="cache",
                    args={"order_by": "a,b", "rows_per_page": "5"},
                    value=None,
                )
            ],
            {"order_by": ["a", "b"], "rows_per_page": "5"},
        ),
    ],
)
def test_build_cache_merges_sources(metadata, directives, expected):
    cache = _build_cache(metadata, directives)
    for key, value in expected.items():
        assert cache and cache[key] == value


@pytest.mark.parametrize(
    "metadata, directives",
    [
        ({"cache": {"enabled": True}}, []),
        ({"cache": {"order_by": []}}, []),
    ],
)
def test_build_cache_requires_order_by(metadata, directives):
    with pytest.raises(RouteCompilationError):
        _build_cache(metadata, directives)


@given(
    st.lists(st.text(min_size=1, max_size=5), min_size=1, max_size=4)
    | st.text(min_size=1, max_size=20)
)
def test_build_cache_normalizes_order_by(values):
    metadata = {"cache": {"order_by": values}}
    cache = _build_cache(metadata, [])
    assert cache is not None
    normalized = cache["order_by"]
    assert isinstance(normalized, list)
    assert all(isinstance(item, str) for item in normalized)


@pytest.mark.parametrize(
    "sql, params, expected_order, expected_sql",
    [
        (
            "SELECT * FROM items WHERE id = {{id}}",
            [ParameterSpec(name="id", type=ParameterType.INTEGER)],
            ["id"],
            "SELECT * FROM items WHERE id = ?",
        ),
        (
            "SELECT $name FROM dual WHERE id = {{id}}",
            [
                ParameterSpec(name="id", type=ParameterType.INTEGER),
                ParameterSpec(name="name"),
            ],
            ["name", "id"],
            "SELECT ? FROM dual WHERE id = ?",
        ),
    ],
)
def test_prepare_sql_translates_placeholders(sql, params, expected_order, expected_sql):
    order, prepared = _prepare_sql(sql, params)
    assert order == expected_order
    assert prepared == expected_sql


@pytest.mark.parametrize(
    "sql, params",
    [
        ("SELECT {{missing}}", []),
        ("SELECT $unknown", [ParameterSpec(name="known")]),
    ],
)
def test_prepare_sql_raises_for_unknown_params(sql, params):
    with pytest.raises(RouteCompilationError):
        _prepare_sql(sql, params)


@st.composite
def sql_placeholder_strategy(draw):
    names = draw(st.lists(st.text(min_size=1, max_size=5), min_size=1, max_size=5))
    unique = {name for name in names}
    params = [ParameterSpec(name=name) for name in sorted(unique)]
    sql = "SELECT " + " + ".join(f"{{{{{name}}}}}" for name in names)
    sql += " FROM dual"
    return sql, params, names


@given(sql_placeholder_strategy())
def test_prepare_sql_tracks_placeholder_order(case):
    sql, params, names = case
    order, prepared = _prepare_sql(sql, params)
    assert order == names
    assert prepared.count("?") == len(names)
