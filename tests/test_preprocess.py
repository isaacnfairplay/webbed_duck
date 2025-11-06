from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pyarrow as pa
import pytest

from tests.conftest import write_sidecar_route
from webbed_duck.core.compiler import RouteCompilationError, compile_routes
from webbed_duck.core.routes import RouteDefinition, load_compiled_routes
from webbed_duck.core.local import run_route
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


def test_run_preprocessors_supports_varied_signatures() -> None:
    route = _make_route_definition()
    steps = [
        {
            "callable": "tests.fake_preprocessors:add_prefix",
            "prefix": "pre-",
            "options": {"prefix": "pre-", "note": "memo"},
        },
        {"callable": "tests.fake_preprocessors:add_suffix", "suffix": "-post"},
        {"callable": "tests.fake_preprocessors:return_none"},
    ]
    result = run_preprocessors(steps, {"name": "value"}, route=route, request=None)
    assert result["name"] == "pre-value-post"
    # note merged from options payload
    assert result["note"] == "memo"


def test_run_preprocessors_supports_file_references(tmp_path: Path) -> None:
    route = _make_route_definition()
    script = tmp_path / "custom_preprocessor.py"
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
    callable_path = f"{os.path.relpath(script)}:append_suffix"
    steps = [{"callable": callable_path, "suffix": "!"}]

    result = run_preprocessors(steps, {"name": "duck"}, route=route, request=None)

    assert result["name"] == "duck!"


def test_run_preprocessors_discovers_package_modules(tmp_path: Path) -> None:
    route = _make_route_definition()
    package_dir = tmp_path / "plugins_pkg"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("\n")
    (package_dir / "decorate.py").write_text(
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

    callable_path = f"{package_dir}:decorate"
    steps = [{"callable": callable_path, "suffix": "?"}]

    result = run_preprocessors(steps, {"name": "duck"}, route=route, request=None)

    assert result["name"] == "duck?"


def test_run_preprocessors_integrates_with_local_runner(tmp_path: Path) -> None:
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
        "<!-- @preprocess {\"callable\": \"tests.fake_preprocessors:uppercase_value\", \"field\": \"name\"} -->\n"
        "```sql\nSELECT {{name}} AS result\n```\n"
    )
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    src_dir.mkdir()
    write_sidecar_route(src_dir, "pre", route_text)
    compile_routes(src_dir, build_dir)
    routes = load_compiled_routes(build_dir)

    table = run_route("pre_route", params={"name": "duck"}, routes=routes, build_dir=build_dir)
    assert isinstance(table, pa.Table)
    assert table.column("result")[0].as_py() == "DUCK"


def test_compile_preprocess_accepts_callable_path(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    plugin_file = plugin_dir / "custom_pre.py"
    plugin_file.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            from typing import Mapping


            def mutate(params: Mapping[str, object], *, suffix: str) -> Mapping[str, object]:
                result = dict(params)
                result["name"] = f"{result.get('name', '')}{suffix}"
                return result
            """
        ).strip()
        + "\n"
    )

    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    src_dir.mkdir()
    (src_dir / "path_demo.sql").write_text("SELECT {{name}} AS name;\n", encoding="utf-8")
    (src_dir / "path_demo.toml").write_text(
        """
id = "path_demo"
path = "/path_demo"

[params.name]
type = "str"

[[preprocess]]
callable_path = "../plugins/custom_pre.py"
callable_name = "mutate"
suffix = "!"
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    compile_routes(src_dir, build_dir)
    routes = load_compiled_routes(build_dir)
    route = next(defn for defn in routes if defn.id == "path_demo")
    assert route.preprocess, "preprocess steps should be compiled"
    step = route.preprocess[0]
    assert step["callable_name"] == "mutate"
    assert step["callable_source_type"] == "path"
    assert Path(step["callable_resolved_path"]).exists()

    result = run_preprocessors([step], {"name": "duck"}, route=route, request=None)
    assert result["name"] == "duck!"


def test_compile_preprocess_accepts_callable_module(tmp_path: Path) -> None:
    pkg_root = tmp_path / "pkg"
    pkg_root.mkdir()
    (pkg_root / "__init__.py").write_text("\n", encoding="utf-8")
    (pkg_root / "helpers.py").write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            from typing import Mapping


            def decorate(params: Mapping[str, object], *, prefix: str) -> Mapping[str, object]:
                result = dict(params)
                result["name"] = f"{prefix}{result.get('name', '')}"
                return result
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    src_dir.mkdir()
    (src_dir / "module_demo.sql").write_text("SELECT {{name}} AS name;\n", encoding="utf-8")
    (src_dir / "module_demo.toml").write_text(
        """
id = "module_demo"
path = "/module_demo"

[params.name]
type = "str"

[[preprocess]]
callable_module = "pkg.helpers"
callable_name = "decorate"
prefix = "pre-"
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        compile_routes(src_dir, build_dir)
    finally:
        sys.path.remove(str(tmp_path))

    routes = load_compiled_routes(build_dir)
    route = next(defn for defn in routes if defn.id == "module_demo")
    assert route.preprocess, "preprocess steps should be compiled"
    step = route.preprocess[0]
    assert step["callable_name"] == "decorate"
    assert step["callable_source_type"] == "module"
    assert Path(step["callable_resolved_path"]).exists()

    result = run_preprocessors([step], {"name": "duck"}, route=route, request=None)
    assert result["name"] == "pre-duck"


def test_compile_preprocess_missing_path_raises(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    src_dir.mkdir()
    (src_dir / "broken.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (src_dir / "broken.toml").write_text(
        """
id = "broken"
path = "/broken"

[[preprocess]]
callable_path = "missing/plugins.py"
callable_name = "noop"
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RouteCompilationError, match="Callable path 'missing/plugins.py'"):
        compile_routes(src_dir, build_dir)


def test_compile_preprocess_missing_callable_raises(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    src_dir.mkdir()
    plugin = src_dir / "unused.py"
    plugin.write_text("value = 1\n", encoding="utf-8")
    (src_dir / "invalid.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (src_dir / "invalid.toml").write_text(
        f"""
id = "invalid"
path = "/invalid"

[[preprocess]]
callable_path = "{plugin.name}"
callable_name = "missing"
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RouteCompilationError, match="Failed to load preprocess callable 'missing'"):
        compile_routes(src_dir, build_dir)
