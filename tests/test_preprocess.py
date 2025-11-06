from __future__ import annotations

import textwrap
from pathlib import Path

import pyarrow as pa

from tests.conftest import write_sidecar_route
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import RouteDefinition, load_compiled_routes
from webbed_duck.core.local import run_route
from webbed_duck.plugins.loader import PluginLoader
from webbed_duck.server.preprocess import run_preprocessors


def _make_route_definition() -> RouteDefinition:
    return RouteDefinition(
        id="example",
        path="/example",
        methods=["GET"],
        raw_sql="SELECT ?",
        prepared_sql="SELECT ?",
        param_order=["name"],
        params=(),
        metadata={},
    )


def _write_fake_plugin(plugins_dir: Path) -> str:
    source = Path(__file__).resolve().parent / "fake_preprocessors.py"
    target = plugins_dir / "fake_preprocessors.py"
    target.write_text(source.read_text())
    return "fake_preprocessors.py"


def test_run_preprocessors_supports_varied_signatures(plugins_dir: Path) -> None:
    route = _make_route_definition()
    plugin_path = _write_fake_plugin(plugins_dir)
    loader = PluginLoader(plugins_dir)
    steps = [
        {
            "callable_path": plugin_path,
            "callable_name": "add_prefix",
            "kwargs": {"prefix": "pre-", "note": "memo"},
        },
        {
            "callable_path": plugin_path,
            "callable_name": "add_suffix",
            "kwargs": {"suffix": "-post"},
        },
        {
            "callable_path": plugin_path,
            "callable_name": "return_none",
        },
    ]
    result = run_preprocessors(
        steps,
        {"name": "value"},
        route=route,
        request=None,
        loader=loader,
    )
    assert result["name"] == "pre-value-post"
    # note merged from options payload
    assert result["note"] == "memo"


def test_run_preprocessors_supports_file_references(plugins_dir: Path) -> None:
    route = _make_route_definition()
    script = plugins_dir / "custom_preprocessor.py"
    script.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            from typing import Mapping

            from webbed_duck.server.preprocess import PreprocessContext


            def append_suffix(params: Mapping[str, object], *, context: PreprocessContext, suffix: str) -> Mapping[str, object]:
                result = dict(params)
                result["name"] = f"{result.get('name', '')}{suffix}"
                return result
            """
        ).strip()
        + "\n"
    )
    loader = PluginLoader(plugins_dir)
    steps = [
        {
            "callable_path": "custom_preprocessor.py",
            "callable_name": "append_suffix",
            "kwargs": {"suffix": "!"},
        }
    ]

    result = run_preprocessors(
        steps,
        {"name": "duck"},
        route=route,
        request=None,
        loader=loader,
    )

    assert result["name"] == "duck!"


def test_run_preprocessors_supports_subdirectories(plugins_dir: Path) -> None:
    route = _make_route_definition()
    subdir = plugins_dir / "time_math"
    subdir.mkdir()
    (subdir / "decorate.py").write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            from typing import Mapping


            def decorate(params: Mapping[str, object], *, suffix: str) -> Mapping[str, object]:
                result = dict(params)
                result["name"] = f"{result.get('name', '')}{suffix}"
                return result
            """
        ).strip()
        + "\n"
    )
    loader = PluginLoader(plugins_dir)
    steps = [
        {
            "callable_path": "time_math/decorate.py",
            "callable_name": "decorate",
            "kwargs": {"suffix": "?"},
        }
    ]

    result = run_preprocessors(
        steps,
        {"name": "duck"},
        route=route,
        request=None,
        loader=loader,
    )

    assert result["name"] == "duck?"


def test_run_preprocessors_integrates_with_local_runner(
    tmp_path: Path, plugins_dir: Path
) -> None:
    plugin_path = _write_fake_plugin(plugins_dir)
    route_text = (
        "+++\n"
        "id = \"pre_route\"\n"
        "path = \"/pre\"\n"
        "[params.name]\n"
        "type = \"str\"\n"
        "required = true\n"
        "[cache]\n"
        "order_by = [\"result\"]\n"
        "+++\n\n"
        f"<!-- @preprocess {{\"callable_path\": \"{plugin_path}\", \"callable_name\": \"uppercase_value\", \"kwargs\": {{\"field\": \"name\"}}}} -->\n"
        "```sql\nSELECT $name AS result\n```\n"
    )
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    src_dir.mkdir()
    write_sidecar_route(src_dir, "pre", route_text)
    compile_routes(src_dir, build_dir, plugins_dir=plugins_dir)
    routes = load_compiled_routes(build_dir)

    table = run_route("pre_route", params={"name": "duck"}, routes=routes, build_dir=build_dir)
    assert isinstance(table, pa.Table)
    assert table.column("result")[0].as_py() == "DUCK"
