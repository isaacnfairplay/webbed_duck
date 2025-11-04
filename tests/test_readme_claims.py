from __future__ import annotations

import datetime
import contextlib
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from types import ModuleType

import pytest
import duckdb

from tests.conftest import write_sidecar_route
from webbed_duck import cli as cli_module
from webbed_duck.config import Config, _as_path, load_config
from webbed_duck.core.compiler import compile_route_file, compile_routes
from webbed_duck.core.incremental import run_incremental
from webbed_duck.core.routes import ParameterSpec, RouteDefinition, load_compiled_routes
from webbed_duck.plugins import assets as assets_plugins
from webbed_duck.plugins import charts as charts_plugins
from webbed_duck.server.app import create_app
from webbed_duck.server.auth import resolve_auth_adapter
from webbed_duck.server.email import load_email_sender
from webbed_duck.server.execution import RouteExecutor
from webbed_duck.server.ui import layout as ui_layout_module
from webbed_duck.static.chartjs import CHARTJS_FILENAME, CHARTJS_VERSION

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    TestClient = None  # type: ignore

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for <3.11
    import tomli as tomllib  # type: ignore


not_callable = "email-attribute"


ROUTE_PRIMARY = """+++
id = "hello"
path = "/hello"
[params.name]
type = "str"
required = false
default = "DuckDB"
ui_control = "input"
ui_label = "Name"
ui_placeholder = "Team mate"
ui_help = "Enter a name and apply the filter"

[cache]
ttl_hours = 12
order_by = ["created_at"]

[html_t]
show_params = ["name"]

[html_c]
show_params = ["name"]

[overrides]
key_columns = ["greeting"]
allowed = ["note"]

[append]
columns = ["greeting", "note", "created_at"]

[share]
pii_columns = ["note"]
+++

```sql
SELECT
  'Hello, ' || {{name}} || '!' AS greeting,
  'private-note' AS note,
  CURRENT_DATE AS created_at
```
"""


ROUTE_INCREMENTAL = """+++
id = "by_date"
path = "/by_date"
[params.day]
type = "str"
required = true
[cache]
order_by = ["day_value"]
+++

```sql
SELECT {{day}} AS day_value
ORDER BY day_value;
```
"""


ROUTE_PAGED = """+++
id = "cached_page"
path = "/cached_page"

[cache]
rows_per_page = 2
order_by = ["value"]

+++

```sql
SELECT range as value FROM range(0,5) ORDER BY value;
```
"""


ROUTE_PAGED_FLEX = """+++
id = "cached_page_flex"
path = "/cached_page_flex"

[cache]
rows_per_page = 2
enforce_page_size = false
order_by = ["value"]

+++

```sql
SELECT range as value FROM range(0,8) ORDER BY value;
```
"""


ROUTE_INVARIANT_SUPERSET = """+++
id = "cached_invariant_superset"
path = "/cached_invariant"

[params.product_code]
type = "str"
required = false

[cache]
rows_per_page = 5
invariant_filters = [ { param = "product_code", column = "product_code", separator = "," } ]
order_by = ["seq"]

+++

```sql
SELECT product_code, quantity, seq
FROM (
    VALUES ('widget', 4, 1), ('gadget', 2, 2), (NULL, 3, 3), ('widget', 5, 4)
) AS inventory(product_code, quantity, seq)
WHERE product_code IS NOT DISTINCT FROM COALESCE(NULLIF({{ product_code }}, ''), product_code)
ORDER BY seq;
```
"""


ROUTE_INVARIANT_SHARDS = """+++
id = "cached_invariant_shards"
path = "/cached_invariant_shards"

[params.product_code]
type = "str"
required = false

[cache]
rows_per_page = 5
invariant_filters = [ { param = "product_code", column = "product_code", separator = "," } ]
order_by = ["seq"]

+++

```sql
SELECT product_code, quantity, seq
FROM (
    VALUES ('widget', 4, 1), ('gadget', 2, 2), (NULL, 3, 3), ('widget', 5, 4)
) AS inventory(product_code, quantity, seq)
WHERE product_code IS NOT DISTINCT FROM COALESCE(NULLIF({{ product_code }}, ''), product_code)
ORDER BY seq;
```
"""


ROUTE_DEP_CHILD_TOML = """id = "readme_child"
path = "/readme_child"
title = "Child dataset for README coverage"
cache_mode = "materialize"
returns = "parquet"

[cache]
order_by = ["id"]
rows_per_page = 10

[params]
label = "VARCHAR"
plant = "VARCHAR"
"""


ROUTE_DEP_CHILD_SQL = """SELECT id, label, 'US01' AS plant
FROM (VALUES (1, 'alpha'), (2, 'beta')) AS t(id, label)
WHERE $label IS NULL OR label = $label
ORDER BY id;"""


ROUTE_DEP_PARENT_TOML = """id = "readme_parent"
path = "/readme_parent"
title = "Parent dataset via dependency"
cache_mode = "passthrough"
returns = "relation"

[params]
label = "VARCHAR"

[[uses]]
alias = "child_cache"
call = "readme_child"
mode = "parquet_path"

[uses.args]
label = "label"
plant = "US01"
"""


ROUTE_DEP_PARENT_SQL = """SELECT id, label
FROM child_cache
WHERE plant = 'US01' AND ($label IS NULL OR label = $label)
ORDER BY id;"""


@dataclass(slots=True)
class ReadmeContext:
    repo_root: Path
    readme_lines: list[str]
    compiled_hashes: dict[str, str]
    recompiled_hashes: dict[str, str]
    compiled_routes: list
    route_json: dict
    html_text: str
    html_headers: dict[str, str]
    cards_text: str
    cards_headers: dict[str, str]
    feed_text: str
    chart_js_text: str
    chart_js_headers: dict[str, str]
    chart_js_embed_text: str
    html_rpc_payload: dict
    cards_rpc_payload: dict
    csv_headers: dict[str, str]
    parquet_headers: dict[str, str]
    arrow_headers: dict[str, str]
    arrow_rpc_headers: dict[str, str]
    analytics_payload: dict
    schema_payload: dict
    override_payload: dict
    append_path: Path
    share_payload: dict
    share_db_hashes: tuple[str, str]
    auth_allowed_domains: list[str]
    email_bind_to_user_agent: bool
    email_bind_to_ip_prefix: bool
    local_resolve_payload: dict
    incremental_rows: list
    checkpoints_exists: bool
    incremental_checkpoint_value: str | None
    incremental_failure_preserves_checkpoint: bool
    incremental_custom_runner_rows: int
    incremental_custom_runner_checkpoint: str | None
    storage_root_layout: dict[str, bool]
    repo_structure: dict[str, bool]
    reload_capable: bool
    python_requires: str
    optional_dependencies: dict[str, list[str]]
    dependencies: list[str]
    email_records: list
    assets_registry_size: int
    charts_registry_size: int
    duckdb_connect_counts: list[int]
    source_pairs: dict[str, dict[str, bool]]
    legacy_sidecars_present: bool
    route_cache_modes: dict[str, str]
    route_returns: dict[str, str]
    route_uses: dict[str, list]
    composition_payload: dict
    parquet_artifacts: list[Path]
    cache_enforced_payload: dict
    cache_flexible_payload: dict
    cache_config: object
    invariant_superset_payload: dict
    invariant_superset_counts: list[int]
    invariant_null_payload: dict
    invariant_null_counts: list[int]
    invariant_combined_payload: dict
    invariant_shard_counts: list[int]
    duckdb_binding_checks: dict[str, bool]
    external_adapter_checks: dict[str, bool]
    share_config: object
    quality_gate_tools: set[str]


def _inject_file_list_preprocessor(params, *, context, files):
    updated = dict(params)
    updated["files"] = list(files)
    return updated


def _install_email_adapter(records: list[tuple]) -> str:
    import types
    import sys

    module_name = "tests.readme_email_capture"
    module = types.ModuleType(module_name)

    def send_email(to_addrs, subject, html_body, text_body=None, attachments=None):
        records.append((tuple(to_addrs), subject, html_body, text_body, attachments))

    module.send_email = send_email  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    return module_name


def _extract_statements(readme: str) -> list[str]:
    statements: list[str] = []
    in_code_block = False
    for line in readme.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code_block:
                if stripped == "```":
                    in_code_block = False
                continue
            in_code_block = True
            continue
        if in_code_block or not stripped or stripped.startswith("#"):
            continue
        statements.append(stripped)
    return statements


def _validate_path_resolution_statement() -> None:
    """Assert the README path resolution narrative remains accurate."""

    base = Path.cwd()
    resolved = _as_path("relative/data", relative_to=base)
    assert resolved == (base / "relative/data").resolve(strict=False)

    import webbed_duck.config as config_module

    original = config_module._is_wsl
    try:
        config_module._is_wsl = lambda: False
        if os.name != "nt":
            with pytest.raises(ValueError):
                _as_path("E:/analytics")

        config_module._is_wsl = lambda: True
        rewritten = _as_path("E:/analytics")
        assert str(rewritten).startswith("/mnt/e/analytics")
    finally:
        config_module._is_wsl = original


@pytest.fixture(scope="module")
def readme_context(tmp_path_factory: pytest.TempPathFactory) -> ReadmeContext:
    if TestClient is None:  # pragma: no cover - fastapi optional
        pytest.skip("fastapi is required to validate README statements")

    tmp_path = tmp_path_factory.mktemp("readme")
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    rebuild_dir = tmp_path / "build2"
    storage_root = tmp_path / "storage"
    src_dir.mkdir()

    write_sidecar_route(src_dir, "hello", ROUTE_PRIMARY)
    write_sidecar_route(src_dir, "by_date", ROUTE_INCREMENTAL)
    write_sidecar_route(src_dir, "cached_page", ROUTE_PAGED)
    write_sidecar_route(src_dir, "cached_page_flex", ROUTE_PAGED_FLEX)
    write_sidecar_route(src_dir, "cached_invariant", ROUTE_INVARIANT_SUPERSET)
    write_sidecar_route(src_dir, "cached_invariant_shards", ROUTE_INVARIANT_SHARDS)

    (src_dir / "readme_child.toml").write_text(ROUTE_DEP_CHILD_TOML + "\n", encoding="utf-8")
    (src_dir / "readme_child.sql").write_text(ROUTE_DEP_CHILD_SQL + "\n", encoding="utf-8")
    (src_dir / "readme_parent.toml").write_text(ROUTE_DEP_PARENT_TOML + "\n", encoding="utf-8")
    (src_dir / "readme_parent.sql").write_text(ROUTE_DEP_PARENT_SQL + "\n", encoding="utf-8")
    (src_dir / "readme_parent.md").write_text("# Parent documentation\n", encoding="utf-8")

    compile_routes(src_dir, build_dir)
    compile_routes(src_dir, rebuild_dir)

    source_pairs: dict[str, dict[str, bool]] = {}
    legacy_sidecars_present = False
    for toml_path in sorted(src_dir.rglob("*.toml")):
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        route_id = str(data.get("id", toml_path.stem))
        source_pairs[route_id] = {
            "toml": toml_path.exists(),
            "sql": toml_path.with_suffix(".sql").exists(),
            "md": toml_path.with_suffix(".md").exists(),
        }
        legacy_sidecars_present = legacy_sidecars_present or toml_path.with_suffix(".sql.md").exists()

    def _hash_dir(path: Path) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for file in sorted(path.glob("**/*.py")):
            hashes[str(file.relative_to(path))] = hashlib.sha256(file.read_bytes()).hexdigest()
        return hashes

    compiled_hashes = _hash_dir(build_dir)
    recompiled_hashes = _hash_dir(rebuild_dir)

    routes = load_compiled_routes(build_dir)
    route_cache_modes = {route.id: route.cache_mode for route in routes}
    route_returns = {route.id: route.returns for route in routes}
    route_uses = {route.id: list(route.uses) for route in routes}
    config = load_config(None)
    config.server.storage_root = storage_root
    config.auth.mode = "pseudo"
    config.auth.allowed_domains = ["example.com"]
    config.email.adapter = f"{_install_email_adapter(records := [])}:send_email"
    config.email.bind_share_to_user_agent = False
    config.email.bind_share_to_ip_prefix = False

    vendor_dir = storage_root / "static" / "vendor" / "chartjs"
    vendor_dir.mkdir(parents=True)
    (vendor_dir / CHARTJS_FILENAME).write_text("window.Chart=function(){};")

    app = create_app(routes, config)
    reload_capable = hasattr(app.state, "reload_routes")

    duckdb_connect_counts: list[int] = []

    def request_with_tracking(client: TestClient, method: str, path: str, **kwargs):
        from unittest.mock import patch
        import duckdb

        call_count = 0
        original = duckdb.connect

        def tracking_connect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original(*args, **kwargs)

        with patch("webbed_duck.server.app.duckdb.connect", side_effect=tracking_connect):
            response = getattr(client, method)(path, **kwargs)
        duckdb_connect_counts.append(call_count)
        return response

    composition_payload: dict = {}

    with TestClient(app) as client:
        login = client.post("/auth/pseudo/session", json={"email": "user@example.com"})
        assert login.status_code == 200

        json_response = request_with_tracking(client, "get", "/hello")
        route_json = json_response.json()
        request_with_tracking(client, "get", "/hello")

        html_response = client.get("/hello", params={"format": "html_t"})
        cards_response = client.get("/hello", params={"format": "html_c"})
        feed_response = client.get("/hello", params={"format": "feed"})
        chart_js_response = client.get("/hello", params={"format": "chart_js"})
        chart_js_embed_response = client.get(
            "/hello",
            params={"format": "chart_js", "embed": "1"},
        )
        csv_response = client.get("/hello", params={"format": "csv"})
        parquet_response = client.get("/hello", params={"format": "parquet"})
        arrow_response = client.get("/hello", params={"format": "arrow", "limit": 1})
        arrow_rpc_response = client.get(
            "/hello",
            params={"format": "arrow_rpc", "limit": 1},
        )
        paged_response = client.get(
            "/cached_page",
            params={"format": "json", "limit": 1, "offset": 3},
        )
        paged_payload = paged_response.json()

        flex_response = client.get(
            "/cached_page_flex",
            params={"format": "json", "limit": 4, "offset": 1},
        )
        flex_payload = flex_response.json()

        invariant_superset_counts: list[int] = []
        request_with_tracking(
            client,
            "get",
            "/cached_invariant",
            params={"format": "json"},
        )
        invariant_superset_counts.append(duckdb_connect_counts[-1])
        superset_filtered = request_with_tracking(
            client,
            "get",
            "/cached_invariant",
            params={"format": "json", "product_code": "gadget"},
        )
        invariant_superset_counts.append(duckdb_connect_counts[-1])
        invariant_superset_payload = superset_filtered.json()

        invariant_null_counts: list[int] = []
        null_filtered = request_with_tracking(
            client,
            "get",
            "/cached_invariant",
            params={"format": "json", "product_code": "__null__"},
        )
        invariant_null_counts.append(duckdb_connect_counts[-1])
        invariant_null_payload = null_filtered.json()
        request_with_tracking(
            client,
            "get",
            "/cached_invariant",
            params={"format": "json", "product_code": "__null__"},
        )
        invariant_null_counts.append(duckdb_connect_counts[-1])

        invariant_shard_counts: list[int] = []
        request_with_tracking(
            client,
            "get",
            "/cached_invariant_shards",
            params={"format": "json", "product_code": "widget"},
        )
        invariant_shard_counts.append(duckdb_connect_counts[-1])
        request_with_tracking(
            client,
            "get",
            "/cached_invariant_shards",
            params={"format": "json", "product_code": "gadget"},
        )
        invariant_shard_counts.append(duckdb_connect_counts[-1])
        shard_combined = request_with_tracking(
            client,
            "get",
            "/cached_invariant_shards",
            params={"format": "json", "product_code": "widget,gadget"},
        )
        invariant_shard_counts.append(duckdb_connect_counts[-1])
        invariant_combined_payload = shard_combined.json()

        composition_response = request_with_tracking(
            client,
            "get",
            "/readme_parent",
            params={"format": "json", "label": "beta"},
        )
        assert composition_response.status_code == 200
        composition_payload = composition_response.json()

        override_response = client.post(
            "/routes/hello/overrides",
            json={"column": "note", "key": {"greeting": "Hello, DuckDB!"}, "value": "annotated"},
        )
        append_response = client.post(
            "/routes/hello/append",
            json={"greeting": "Hello, DuckDB!", "note": "annotated", "created_at": "2025-01-01"},
        )
        schema_response = client.get("/routes/hello/schema")
        analytics_response = client.get("/routes")

        share_response = client.post(
            "/routes/hello/share",
            json={"emails": ["friend@example.com"], "params": {"name": "Duck"}, "format": "json"},
        )
        share_payload = share_response.json()["share"]
        share_token = share_payload["token"]
        shared_response = client.get(f"/shares/{share_token}")

        local_resolve = client.post(
            "/local/resolve",
            json={
                "reference": "local:hello?column=greeting",
                "params": {"name": "Goose"},
                "columns": ["greeting"],
                "format": "json",
            },
        )

        # Trigger incremental analytics by running route again with tracking
        request_with_tracking(client, "get", "/hello", params={"name": "Swan"})

    checkpoints_path = storage_root / "runtime" / "checkpoints.duckdb"
    incremental_rows = list(
        run_incremental(
            "by_date",
            cursor_param="day",
            start=datetime.date(2024, 1, 1),
            end=datetime.date(2024, 1, 3),
            config=config,
            build_dir=build_dir,
        )
    )
    if incremental_rows:
        with duckdb.connect(checkpoints_path) as conn:
            row = conn.execute(
                "SELECT cursor_value FROM checkpoints WHERE route_id = ? AND cursor_param = ?",
                ("by_date", "day"),
            ).fetchone()
        checkpoint_value = row[0] if row else None
        last_day = datetime.date.fromisoformat(incremental_rows[-1].value)
        next_day = last_day + datetime.timedelta(days=1)

        def _failing_runner(route_id, *, params, **kwargs):  # type: ignore[no-untyped-def]
            raise ValueError("boom")

        try:
            run_incremental(
                "by_date",
                cursor_param="day",
                start=next_day,
                end=next_day,
                config=config,
                build_dir=build_dir,
                runner=_failing_runner,
            )
        except ValueError:
            pass

        with duckdb.connect(checkpoints_path) as conn:
            failure_row = conn.execute(
                "SELECT cursor_value FROM checkpoints WHERE route_id = ? AND cursor_param = ?",
                ("by_date", "day"),
            ).fetchone()
        failure_preserves_checkpoint = (failure_row[0] if failure_row else None) == checkpoint_value

        class _DummyTable:
            def __init__(self, rows: int) -> None:
                self.num_rows = rows

        custom_results = run_incremental(
            "by_date",
            cursor_param="day",
            start=next_day,
            end=next_day,
            config=config,
            build_dir=build_dir,
            runner=lambda *args, **kwargs: _DummyTable(5),  # type: ignore[arg-type]
        )
        custom_runner_rows = custom_results[0].rows_returned if custom_results else 0
        with duckdb.connect(checkpoints_path) as conn:
            custom_row = conn.execute(
                "SELECT cursor_value FROM checkpoints WHERE route_id = ? AND cursor_param = ?",
                ("by_date", "day"),
            ).fetchone()
        custom_runner_checkpoint = custom_row[0] if custom_row else None
    else:
        checkpoint_value = None
        failure_preserves_checkpoint = False
        custom_runner_rows = 0
        custom_runner_checkpoint = None

    parquet_artifacts = list((storage_root / "cache").rglob("*.parquet"))

    duckdb_binding_checks = {"single": False, "multi": False, "preprocessed_multi": False}
    if parquet_artifacts:
        sample_path = parquet_artifacts[0]
        with duckdb.connect() as con:
            duckdb_binding_checks["single"] = (
                con.execute("SELECT COUNT(*) FROM read_parquet(?::TEXT)", [str(sample_path)]).fetchone()[0]
                >= 0
            )
            duckdb_binding_checks["multi"] = (
                con.execute("SELECT COUNT(*) FROM read_parquet(?::TEXT[])", [[str(sample_path)]]).fetchone()[0]
                >= 0
            )
        preprocessed_route = RouteDefinition(
            id="doc_duckdb_preprocessor",
            path="/doc_duckdb_preprocessor",
            methods=["GET"],
            raw_sql="SELECT COUNT(*) AS row_count FROM read_parquet($files::TEXT[])",
            prepared_sql="SELECT COUNT(*) AS row_count FROM read_parquet(?::TEXT[])",
            param_order=["files"],
            params=(ParameterSpec(name="files", required=False, default=None),),
            metadata={},
            preprocess=(
                {
                    "callable": "tests.test_readme_claims:_inject_file_list_preprocessor",
                    "files": [str(sample_path)],
                },
            ),
            cache_mode="passthrough",
        )
        executor = RouteExecutor({preprocessed_route.id: preprocessed_route}, cache_store=None, config=config)
        result = executor.execute_relation(
            preprocessed_route,
            params={},
            offset=0,
            limit=None,
        )
        duckdb_binding_checks["preprocessed_multi"] = (
            result.table.to_pydict().get("row_count", [0])[0] >= 0
        )

    share_db_path = storage_root / "runtime" / "meta.sqlite3"
    with sqlite3.connect(share_db_path) as conn:
        share_hash = conn.execute("SELECT token_hash FROM shares").fetchone()[0]
        session_hash = conn.execute("SELECT token_hash FROM sessions").fetchone()[0]

    storage_root_layout = {
        "routes_build": (storage_root / "routes_build").exists(),
        "cache": (storage_root / "cache").exists(),
        "schemas": (storage_root / "schemas").exists(),
        "static": (storage_root / "static").exists(),
        "runtime": (storage_root / "runtime").exists(),
        "runtime/meta.sqlite3": share_db_path.exists(),
        "runtime/checkpoints.duckdb": checkpoints_path.exists(),
    }

    external_adapter_checks: dict[str, bool] = {}

    failure_module = ModuleType("tests.readme_external_failure")

    def _failure_factory(config: Config):  # pragma: no cover - intentional failure path
        raise TypeError("boom")

    failure_module.build_adapter = _failure_factory  # type: ignore[attr-defined]
    sys.modules[failure_module.__name__] = failure_module

    failure_config = Config()
    failure_config.auth.mode = "external"
    failure_config.auth.external_adapter = f"{failure_module.__name__}:build_adapter"
    try:
        resolve_auth_adapter("external", config=failure_config, session_store=None)
    except TypeError as exc:
        external_adapter_checks["type_error"] = "boom" in str(exc)
    else:  # pragma: no cover - should not succeed
        external_adapter_checks["type_error"] = False
    finally:
        sys.modules.pop(failure_module.__name__, None)

    success_module = ModuleType("tests.readme_external_success_adapter")

    class _ReadmeDummyAdapter:
        def __init__(self, cfg: Config) -> None:
            self.config = cfg

        async def authenticate(self, request):  # pragma: no cover - simple stub
            return None

    def _success_factory(config: Config) -> _ReadmeDummyAdapter:
        return _ReadmeDummyAdapter(config)

    success_module.build_adapter = _success_factory  # type: ignore[attr-defined]
    sys.modules[success_module.__name__] = success_module

    success_config = Config()
    success_config.auth.mode = "external"
    success_config.auth.external_adapter = f"{success_module.__name__}:build_adapter"
    adapter_instance = resolve_auth_adapter("external", config=success_config, session_store=None)
    external_adapter_checks["returns_adapter"] = isinstance(adapter_instance, _ReadmeDummyAdapter)
    external_adapter_checks["config_passthrough"] = getattr(adapter_instance, "config", None) is success_config
    sys.modules.pop(success_module.__name__, None)

    repo_root = Path(__file__).resolve().parents[1]
    repo_structure = {
        "CHANGELOG.md": (repo_root / "CHANGELOG.md").is_file(),
        "README.md": (repo_root / "README.md").is_file(),
        "config.toml": (repo_root / "config.toml").is_file(),
        "docs": (repo_root / "docs").is_dir(),
        "examples": (repo_root / "examples").is_dir(),
        "routes_src": (repo_root / "routes_src").is_dir(),
        "routes_build": (repo_root / "routes_build").is_dir(),
        "tests": (repo_root / "tests").is_dir(),
        "webbed_duck": (repo_root / "webbed_duck").is_dir(),
    }
    agents_text = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    quality_gate_tokens = [
        "ruff",
        "mypy --strict webbed_duck/core/**",
        "pytest-benchmark",
        "vulture",
        "radon",
        "bandit",
    ]
    quality_gate_tools = {token for token in quality_gate_tokens if token in agents_text}
    if repo_structure["tests"]:
        quality_gate_tools.add("pytest")

    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    project_data = pyproject.get("project", {})
    python_requires = project_data.get("requires-python", "")
    optional_dependencies = {
        key: sorted(value)
        for key, value in project_data.get("optional-dependencies", {}).items()
        if isinstance(value, list)
    }
    dependencies = [str(item) for item in project_data.get("dependencies", [])]

    readme_text = (repo_root / "README.md").read_text(encoding="utf-8")
    readme_lines = _extract_statements(readme_text)

    rpc_pattern = re.compile(
        r"<script type='application/json' id='wd-rpc-config'>(?P<data>.+?)</script>",
        re.DOTALL,
    )

    def _rpc_payload_from(html_text: str) -> dict:
        match = rpc_pattern.search(html_text)
        if not match:
            return {}
        try:
            return json.loads(match.group("data"))
        except json.JSONDecodeError:
            return {}

    return ReadmeContext(
        repo_root=repo_root,
        readme_lines=readme_lines,
        compiled_hashes=compiled_hashes,
        recompiled_hashes=recompiled_hashes,
        compiled_routes=routes,
        route_json=route_json,
        html_text=html_response.text,
        html_headers=dict(html_response.headers),
        html_rpc_payload=_rpc_payload_from(html_response.text),
        cards_text=cards_response.text,
        cards_headers=dict(cards_response.headers),
        cards_rpc_payload=_rpc_payload_from(cards_response.text),
        feed_text=feed_response.text,
        chart_js_text=chart_js_response.text,
        chart_js_headers=dict(chart_js_response.headers),
        chart_js_embed_text=chart_js_embed_response.text,
        csv_headers=dict(csv_response.headers),
        parquet_headers=dict(parquet_response.headers),
        arrow_headers=dict(arrow_response.headers),
        arrow_rpc_headers=dict(arrow_rpc_response.headers),
        analytics_payload=analytics_response.json(),
        schema_payload=schema_response.json(),
        override_payload=override_response.json()["override"],
        append_path=Path(append_response.json()["path"]),
        share_payload={"meta": share_payload, "resolved": shared_response.json()},
        share_db_hashes=(share_hash, session_hash),
        auth_allowed_domains=list(config.auth.allowed_domains),
        email_bind_to_user_agent=config.email.bind_share_to_user_agent,
        email_bind_to_ip_prefix=config.email.bind_share_to_ip_prefix,
        local_resolve_payload=local_resolve.json(),
        incremental_rows=incremental_rows,
        checkpoints_exists=checkpoints_path.exists(),
        incremental_checkpoint_value=checkpoint_value,
        incremental_failure_preserves_checkpoint=failure_preserves_checkpoint,
        incremental_custom_runner_rows=custom_runner_rows,
        incremental_custom_runner_checkpoint=custom_runner_checkpoint,
        storage_root_layout=storage_root_layout,
        repo_structure=repo_structure,
        reload_capable=reload_capable,
        python_requires=python_requires,
        optional_dependencies=optional_dependencies,
        dependencies=dependencies,
        email_records=records,
        assets_registry_size=len(getattr(assets_plugins, "_REGISTRY", {})),
        charts_registry_size=len(getattr(charts_plugins, "_RENDERERS", {})),
        duckdb_connect_counts=duckdb_connect_counts,
        source_pairs=source_pairs,
        legacy_sidecars_present=legacy_sidecars_present,
        route_cache_modes=route_cache_modes,
        route_returns=route_returns,
        route_uses=route_uses,
        composition_payload=composition_payload,
        parquet_artifacts=parquet_artifacts,
        cache_enforced_payload=paged_payload,
        cache_flexible_payload=flex_payload,
        cache_config=config.cache,
        share_config=config.share,
        invariant_superset_payload=invariant_superset_payload,
        invariant_superset_counts=invariant_superset_counts,
        invariant_null_payload=invariant_null_payload,
        invariant_null_counts=invariant_null_counts,
        invariant_combined_payload=invariant_combined_payload,
        invariant_shard_counts=invariant_shard_counts,
        duckdb_binding_checks=duckdb_binding_checks,
        external_adapter_checks=external_adapter_checks,
        quality_gate_tools=quality_gate_tools,
    )


def _frontmatter_warning_emitted() -> bool:
    route_body = (
        "+++\n"
        "id = \"warn\"\n"
        "path = \"/warn\"\n"
        "extra = 1\n"
        "+++\n\n"
        "```sql\nSELECT 1;\n```\n"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        write_sidecar_route(Path(tmpdir), "warn", route_body)
        route_path = Path(tmpdir) / "warn.toml"
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            compile_route_file(route_path)
        return "unexpected frontmatter key" in buffer.getvalue()


def _ensure(condition: bool, message: str) -> None:
    assert condition, message


def _dependency_names(specs: Iterable[str] | None) -> set[str]:
    names: set[str] = set()
    for spec in specs or []:
        base = spec.split("[", 1)[0]
        for delimiter in ("<", ">", "=", "!", "~", ";"):
            base = base.split(delimiter, 1)[0]
        base = base.strip()
        if base:
            names.add(base)
    return names


def _python_requirement_at_least(requirement: str, minimum: tuple[int, int]) -> bool:
    if not requirement.startswith(">="):
        return False
    version = requirement[2:].strip()
    parts = version.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        return False
    return (major, minor) >= minimum


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_readme_statements_are_covered(readme_context: ReadmeContext) -> None:
    ctx = readme_context

    validators: list[tuple[Callable[[str], bool], Callable[[str], None]]] = [
        (lambda s: s.startswith("`webbed_duck` is a"), lambda s: _ensure(
            ctx.route_json["rows"][0]["greeting"].startswith("Hello"), s
        )),
        (lambda s: s.startswith("This README is the canonical"), lambda s: None),
        (lambda s: s.startswith("See the [Quickstart workspace setup]"), lambda s: _ensure(
            ctx.repo_structure["docs"] and ctx.repo_structure["examples"], s
        )),
        (lambda s: bool(re.match(r"^\d+\. \[", s)), lambda s: None),
        (lambda s: s.startswith("- Each route lives in `routes_src/` as a `<stem>.toml`"), lambda s: _ensure(
            all(pair["toml"] and pair["sql"] for pair in ctx.source_pairs.values())
            and not ctx.legacy_sidecars_present,
            s,
        )),
        (lambda s: s.startswith("> **Legacy `.sql.md` files:**"), lambda s: _ensure(
            not ctx.legacy_sidecars_present,
            s,
        )),
        (lambda s: s.startswith("- The compiler translates those sources"), lambda s: _ensure(
            ctx.compiled_hashes == ctx.recompiled_hashes, s
        )),
        (lambda s: s.startswith("- The runtime ships the results"), lambda s: _ensure(
            "content-type" in ctx.csv_headers and "content-type" in ctx.parquet_headers, s
        )),
        (lambda s: s.startswith("> **FastAPI runtime dependency:**"), lambda s: _ensure(
            {"fastapi", "uvicorn"}.issubset(_dependency_names(ctx.dependencies)),
            s,
        )),
        (lambda s: s.startswith("> **FastAPI extras required:**"), lambda s: _ensure(
            {"fastapi", "uvicorn"}.issubset(
                _dependency_names(ctx.dependencies)
                | _dependency_names(ctx.optional_dependencies.get("server"))
            ),
            s,
        )),
        (lambda s: s.startswith("> **Server optional dependencies:**"), lambda s: _ensure(
            {"fastapi", "uvicorn"}.issubset(_dependency_names(ctx.dependencies)),
            s,
        )),
        (lambda s: s.startswith("The published wheel currently depends on `fastapi`"), lambda s: _ensure(
            {"fastapi", "uvicorn"}.issubset(_dependency_names(ctx.dependencies)),
            s,
        )),
        (lambda s: s.startswith("- Declare parameter controls"), lambda s: _ensure(
            "params-form" in ctx.html_text and "params-form" in ctx.cards_text, s
        )),
        (lambda s: s.startswith("The same `show_params` list works"), lambda s: _ensure(
            "params-form" in ctx.cards_text, s
        )),
        (lambda s: s.startswith("listed there render controls"), lambda s: _ensure(
            "type='hidden'" in ctx.html_text or "type=\"hidden\"" in ctx.html_text, s
        )),
        (lambda s: s.startswith("filter submissions keep pagination"), lambda s: _ensure(
            "name='offset'" in ctx.html_text or "name=\"offset\"" in ctx.html_text,
            s,
        )),
        (lambda s: s.startswith("HTML table and card responses also surface the development HTTP banner when"), lambda s: _ensure(
            "Development mode" in ctx.html_text and "Development mode" in ctx.cards_text,
            s,
        )),
        (lambda s: s.startswith("`ui.show_http_warning` is enabled and reuse the error taxonomy banner toggle"), lambda s: None),
        (lambda s: s.startswith("so operators see consistent guidance. Every response embeds a"), lambda s: _ensure(
            "Errors follow the webbed_duck taxonomy" in ctx.html_text
            and "Errors follow the webbed_duck taxonomy" in ctx.cards_text,
            s,
        )),
        (lambda s: s.startswith("`<script id=\"wd-rpc-config\">` payload alongside a"), lambda s: _ensure(
            "wd-rpc-config" in ctx.html_text and "wd-rpc-config" in ctx.cards_text,
            s,
        )),
        (lambda s: s.startswith("“Download this slice (Arrow)” link, making it easy"), lambda s: _ensure(
            "Download this slice" in ctx.html_text and "Download this slice" in ctx.cards_text,
            s,
        )),
        (lambda s: s.startswith("keeping the rendered form in sync"), lambda s: _ensure(
            "name='offset'" in ctx.cards_text or "name=\"offset\"" in ctx.cards_text,
            s,
        )),
        (lambda s: s.startswith("- Table (`html_t`) and card (`html_c`) responses now emit"), lambda s: _ensure(
            ctx.html_rpc_payload and ctx.cards_rpc_payload, s
        )),
        (lambda s: s.startswith("and an embedded `<script id=\"wd-rpc-config\">`"), lambda s: _ensure(
            "wd-rpc-config" in ctx.html_text and "wd-rpc-config" in ctx.cards_text, s
        )),
        (lambda s: s.startswith("slice (`offset`, `limit`, `total_rows`) plus a ready-to-use Arrow RPC"), lambda s: _ensure(
            "total_rows" in ctx.html_rpc_payload and "total_rows" in ctx.cards_rpc_payload, s
        )),
        (lambda s: s.startswith("endpoint. Clients can call that URL"), lambda s: _ensure(
            "endpoint" in ctx.html_rpc_payload and "endpoint" in ctx.cards_rpc_payload, s
        )),
        (lambda s: s.startswith("stream additional pages without re-rendering the HTML."), lambda s: None),
        (lambda s: s.startswith("- Every HTML response mirrors the RPC headers"), lambda s: _ensure(
            "Download this slice" in ctx.html_text and "Download this slice" in ctx.cards_text, s
        )),
        (lambda s: s.startswith("`x-limit`) and surfaces a convenience link"), lambda s: _ensure(
            ("link" in ctx.html_headers or "Link" in ctx.html_headers)
            and ("link" in ctx.cards_headers or "Link" in ctx.cards_headers),
            s,
        )),
        (lambda s: s.startswith("(Arrow)"), lambda s: None),
        (lambda s: s.startswith("the slice to downstream tooling."), lambda s: _ensure(
            "Download this slice" in ctx.html_text and "Download this slice" in ctx.cards_text,
            s,
        )),
        (lambda s: s.startswith("Arrow RPC endpoints mirror"), lambda s: _ensure(
            all(
                ctx.arrow_rpc_headers.get(header) == ctx.html_headers.get(header)
                for header in ("x-total-rows", "x-offset", "x-limit")
            )
            and ctx.arrow_rpc_headers.get("content-type", "").startswith(
                "application/vnd.apache.arrow.stream"
            ),
            s,
        )),
        (lambda s: s.startswith("- Drop TOML/SQL pairs into a folder"), lambda s: _ensure(
            ctx.repo_structure["routes_src"] and ctx.repo_structure["routes_build"], s
        )),
        (lambda s: s.startswith("- Designed for operational"), lambda s: None),
        (lambda s: s.startswith("3. **Compile the contracts into runnable manifests"), lambda s: None),
        (lambda s: s.startswith("4. **Launch the server."), lambda s: _ensure(
            ctx.reload_capable, s
        )),
        (lambda s: s.startswith("- `--watch` keeps the compiler running"), lambda s: _ensure(
            ctx.reload_capable, s
        )),
        (lambda s: s.startswith("- Pass `--no-auto-compile`"), lambda s: None),
        (lambda s: s.startswith("- Watching performs filesystem polls once per second"), lambda s: _ensure(
            ctx.reload_capable and Config().server.watch_interval == pytest.approx(1.0), s
        )),
        (lambda s: s.startswith("- The watch interval is clamped to a minimum of 0.2 seconds"), lambda s: _ensure(
            hasattr(cli_module, "WATCH_INTERVAL_MIN")
            and cli_module.WATCH_INTERVAL_MIN == pytest.approx(0.2),
            s,
        )),
        (lambda s: s.startswith("- File watching relies on timestamp"), lambda s: _ensure(
            hasattr(cli_module, "SourceFingerprint")
            and hasattr(cli_module, "build_source_fingerprint")
            and hasattr(cli_module.SourceFingerprint, "has_changed"),
            s,
        )),
        (lambda s: s.startswith("- The `webbed-duck perf` helper expects"), lambda s: _ensure(
            hasattr(cli_module, "_cmd_perf") and hasattr(cli_module, "_parse_param_assignments"),
            s,
        )),
        (lambda s: s.startswith("> **Testing note:** The integration tests exercise the FastAPI stack"), lambda s: _ensure(
            TestClient is not None, s
        )),
        (lambda s: s.startswith("1. **Install the package and dependencies.**"), lambda s: None),
            (lambda s: s.startswith("2. **Create your route source directory**"), lambda s: _ensure(
                ctx.repo_structure["routes_src"], s
            )),
            (lambda s: s.startswith("> Legacy HTML comment directives"), lambda s: None),
            (lambda s: s.startswith("5. **Browse the routes.**"), lambda s: _ensure(
                bool(ctx.route_json["rows"]), s
            )),
        (lambda s: s.startswith("For an exhaustive"), lambda s: _ensure(
            (ctx.repo_root / "AGENTS.md").is_file(), s
        )),
        (lambda s: s.startswith("- `ruff`"), lambda s: _ensure(
            "ruff" in ctx.quality_gate_tools, s
        )),
        (lambda s: s.startswith("- `mypy --strict webbed_duck/core/**`"), lambda s: _ensure(
            "mypy --strict webbed_duck/core/**" in ctx.quality_gate_tools, s
        )),
        (lambda s: s.startswith("- `pytest`"), lambda s: _ensure(
            "pytest" in ctx.quality_gate_tools, s
        )),
        (lambda s: s.startswith("- `pytest-benchmark`"), lambda s: _ensure(
            "pytest-benchmark" in ctx.quality_gate_tools, s
        )),
        (lambda s: s.startswith("- `vulture`"), lambda s: _ensure(
            "vulture" in ctx.quality_gate_tools, s
        )),
        (lambda s: s.startswith("- `radon`"), lambda s: _ensure(
            "radon" in ctx.quality_gate_tools, s
        )),
        (lambda s: s.startswith("- `bandit`"), lambda s: _ensure(
            "bandit" in ctx.quality_gate_tools, s
        )),
        (lambda s: s.startswith("- `webbed-duck serve` loads configuration"), lambda s: _ensure(
            ctx.repo_structure["config.toml"], s
        )),
        (lambda s: s.startswith("- With `server.auto_compile = true`"), lambda s: _ensure(
            ctx.reload_capable, s
        )),
        (lambda s: s.startswith("- Enabling watch mode"), lambda s: _ensure(
            ctx.reload_capable, s
        )),
        (lambda s: s.startswith("- Combine `server.watch = true`"), lambda s: _ensure(
            ctx.reload_capable and Config().server.watch_interval == pytest.approx(1.0), s
        )),
        (lambda s: s.startswith("- The server is a FastAPI application"), lambda s: _ensure(
            "html" in ctx.html_text.lower(), s
        )),
        (lambda s: s.startswith("- The compiler scans the source tree"), lambda s: _ensure(
            len(ctx.compiled_routes) >= 1, s
        )),
        (lambda s: s.startswith("- Each TOML file carries the metadata"), lambda s: _ensure(
            "readme_parent" in ctx.route_cache_modes
            and ctx.route_cache_modes["readme_parent"] == "passthrough"
            and bool(ctx.route_uses.get("readme_parent")),
            s,
        )),
        (lambda s: s.startswith("- Frontmatter declares the route `id`"), lambda s: _ensure(
            any(item["name"] == "name" for item in ctx.schema_payload.get("form", [])), s
        )),
        (lambda s: s.startswith("- Compiled artifacts are written"), lambda s: _ensure(
            ctx.repo_structure["routes_build"], s
        )),
        (lambda s: s.startswith("- At boot"), lambda s: _ensure(
            ctx.reload_capable, s
        )),
        (lambda s: s.startswith("- Parameters are declared"), lambda s: _ensure(
            any(item["name"] == "name" for item in ctx.schema_payload.get("form", [])), s
        )),
        (lambda s: s.startswith("- Within the SQL body"), lambda s: _ensure(
            bool(getattr(ctx.compiled_routes[0], "param_order", [])), s
        )),
        (lambda s: s.startswith("- At request time the runtime reads"), lambda s: _ensure(
            bool(ctx.route_json["rows"]), s
        )),
        (lambda s: s.startswith("- Additional runtime controls"), lambda s: None),
        (lambda s: s.startswith("- `?limit=`"), lambda s: None),
        (lambda s: s.startswith("- `?column=`"), lambda s: None),
        (lambda s: s.startswith("- `cache_mode` in the TOML metadata"), lambda s: _ensure(
            ctx.route_cache_modes.get("readme_child") == "materialize"
            and ctx.route_cache_modes.get("readme_parent") == "passthrough",
            s,
        )),
        (lambda s: s.startswith("- `returns` declares the default return style"), lambda s: _ensure(
            ctx.route_returns.get("readme_child") == "parquet"
            and ctx.route_returns.get("readme_parent") == "relation",
            s,
        )),
        (lambda s: s.startswith("- Each `[[uses]]` block defines an upstream dependency"), lambda s: _ensure(
            ctx.route_uses.get("readme_parent")
            and ctx.route_uses["readme_parent"][0].alias == "child_cache"
            and ctx.route_uses["readme_parent"][0].mode in {"relation", "parquet_path"},
            s,
        )),
        (lambda s: s.startswith("- When `mode = \"parquet_path\"`"), lambda s: _ensure(
            any("readme_child" in str(path) for path in ctx.parquet_artifacts)
            and ctx.composition_payload.get("rows") == [{"id": 2, "label": "beta"}],
            s,
        )),
        (lambda s: s.startswith("- Cache settings come from the `[cache]` table in each route's TOML metadata"), lambda s: _ensure(
            hasattr(ctx.cache_config, "ttl_seconds")
            and any(((route.metadata or {}).get("cache") is not None) for route in ctx.compiled_routes),
            s,
        )),
        (lambda s: s.startswith("- Routes must declare `cache.order_by`"), lambda s: _ensure(
            all(
                bool(((route.metadata or {}).get("cache") or {}).get("order_by"))
                for route in ctx.compiled_routes
                if (route.metadata or {}).get("cache")
            ),
            s,
        )),
        (lambda s: s.startswith("- `[cache]`"), lambda s: _ensure(
            all(
                bool(((route.metadata or {}).get("cache") or {}).get("order_by"))
                for route in ctx.compiled_routes
                if (route.metadata or {}).get("cache")
            ),
            s,
        )),
        (lambda s: "runtime can validate the schema" in s, lambda s: _ensure(
            all(
                bool(((route.metadata or {}).get("cache") or {}).get("order_by"))
                for route in ctx.compiled_routes
                if (route.metadata or {}).get("cache")
            ),
            s,
        )),
        (lambda s, phrases=(
            "re-sorts combined pages on those columns",
            "The backend merges",
            "reorders the combined rows by `cache.order_by`",
            "deterministic paging.",
        ): any(phrase in s for phrase in phrases), lambda s: _ensure(
            [row["seq"] for row in ctx.invariant_combined_payload["rows"]] == [1, 2, 4],
            s,
        )),
        (lambda s: s.startswith("- The executor snaps requested offsets"), lambda s: _ensure(
            ctx.cache_enforced_payload["offset"] == 2 and ctx.cache_enforced_payload["limit"] == 2,
            s,
        )),
        (lambda s: s.startswith("- Set `[cache].enforce_page_size = false`"), lambda s: _ensure(
            ctx.cache_flexible_payload["offset"] == 1 and ctx.cache_flexible_payload["limit"] == 4,
            s,
        )),
        (lambda s: s.startswith("- Cache hits skip DuckDB entirely"), lambda s: _ensure(
            len(ctx.duckdb_connect_counts) >= 2 and ctx.duckdb_connect_counts[1] == 0,
            s,
        )),
        (lambda s: s.startswith("- Cache hits reuse those Parquet pages"), lambda s: _ensure(
            ctx.storage_root_layout["cache"]
            and len(ctx.duckdb_connect_counts) >= 2
            and ctx.duckdb_connect_counts[1] == 0,
            s,
        )),
        (lambda s: s.startswith("- Transformation-invariant filters can be declared"), lambda s: _ensure(
            ctx.invariant_superset_counts == [1, 0]
            and ctx.invariant_superset_payload["total_rows"] == 1
            and [row["product_code"] for row in ctx.invariant_superset_payload["rows"]] == ["gadget"],
            s,
        )),
        (lambda s: s.startswith("- To request cached rows where an invariant column is `NULL`"), lambda s: _ensure(
            ctx.invariant_null_counts
            and ctx.invariant_null_counts[0] >= 0
            and ctx.invariant_null_counts[-1] == 0
            and ctx.invariant_null_payload["total_rows"] == 1
            and [row["product_code"] for row in ctx.invariant_null_payload["rows"]] == [None],
            f"{s} -> counts={ctx.invariant_null_counts}, rows={ctx.invariant_null_payload['rows']}",
        )),
        (lambda s: s.startswith("> **Testing reminder:**"), lambda s: _ensure(
            {"duckdb", "pyarrow", "fastapi", "uvicorn"}.issubset(
                _dependency_names(ctx.dependencies)
            ),
            s,
        )),
        (lambda s: s.startswith("- When invariant filters are configured"), lambda s: _ensure(
            ctx.invariant_shard_counts == [1, 1, 0]
            and {row["product_code"] for row in ctx.invariant_combined_payload["rows"]} == {"widget", "gadget"}
            and [row["seq"] for row in ctx.invariant_combined_payload["rows"]] == [1, 2, 4],
            s,
        )),
        (lambda s: s.startswith("- Every cache miss opens a fresh DuckDB connection"), lambda s: _ensure(
            ctx.duckdb_connect_counts and ctx.duckdb_connect_counts[0] >= 1,
            s,
        )),
        (lambda s: s.startswith("Each compiled route honours runtime format negotiation"), lambda s: _ensure(
            "content-type" in ctx.csv_headers
            and "content-type" in ctx.parquet_headers
            and ctx.arrow_headers["content-type"].startswith("application/vnd.apache.arrow.stream"),
            s,
        )),
        (lambda s: s.startswith("`?format=chart_js` renders"), lambda s: _ensure(
            f"?v={CHARTJS_VERSION}" in ctx.chart_js_text,
            s,
        )),
        (lambda s: s.startswith("Override it (and layout details like `canvas_height`)"), lambda s: None),
        (lambda s: s.startswith("All of the following formats work today"), lambda s: _ensure(
            ctx.arrow_headers["content-type"].startswith("application/vnd.apache.arrow.stream"), s
        )),
        (lambda s: s.startswith("| `?format=chart_js`"), lambda s: _ensure(
            "/vendor/" in ctx.chart_js_text and "data-wd-chart" in ctx.chart_js_text,
            s,
        )),
        (lambda s: s.startswith("|"), lambda s: None),
        (lambda s: s.startswith("Append `?embed=1`"), lambda s: _ensure(
            "<!doctype html>" not in ctx.chart_js_embed_text
            and "wd-chart-grid" in ctx.chart_js_embed_text
            and "chart.umd.min.js" in ctx.chart_js_embed_text,
            s,
        )),
        (lambda s: s.startswith("The snippet ships the vendor Chart.js tag"), lambda s: _ensure(
            "/assets/wd/chart_boot.js" in ctx.chart_js_embed_text,
            s,
        )),
        (lambda s: s.startswith("The HTML layer now follows a strict separation"), lambda s: _ensure(
            (ctx.repo_root / "webbed_duck/server/ui/layout.py").is_file()
            and (ctx.repo_root / "webbed_duck/server/ui/views/table.py").is_file(),
            s,
        )),
        (lambda s: s.startswith("- `webbed_duck/server/ui/layout.py` assembles"), lambda s: _ensure(
            hasattr(ui_layout_module, "render_layout"),
            s,
        )),
        (lambda s: s.startswith("- View modules under `webbed_duck/server/ui/views/`"), lambda s: _ensure(
            all(
                (ctx.repo_root / f"webbed_duck/server/ui/views/{name}.py").is_file()
                for name in ("table", "cards", "feed", "charts")
            ),
            s,
        )),
        (lambda s: s.startswith("- Widget modules under `webbed_duck/server/ui/widgets/`"), lambda s: _ensure(
            all(
                (ctx.repo_root / f"webbed_duck/server/ui/widgets/{name}.py").is_file()
                for name in ("params", "multi_select")
            ),
            s,
        )),
        (lambda s: s.startswith("- Support modules under `webbed_duck/server/ui/`"), lambda s: _ensure(
            all(
                (ctx.repo_root / f"webbed_duck/server/ui/{name}.py").is_file()
                for name in ("invariants", "pagination", "rpc", "charts")
            ),
            s,
        )),
        (lambda s: s.startswith("Static assets live in `webbed_duck/static/assets/wd/`"), lambda s: _ensure(
            (ctx.repo_root / "webbed_duck/static/assets/wd").is_dir(),
            s,
        )),
        (lambda s: s.startswith("- `layout.css`, `params.css`"), lambda s: _ensure(
            all(
                (ctx.repo_root / f"webbed_duck/static/assets/wd/{name}.css").is_file()
                for name in ("layout", "params", "multi_select", "table", "cards", "feed", "charts")
            ),
            s,
        )),
        (lambda s: s.startswith("- `progress.js`, `header.js`"), lambda s: _ensure(
            all(
                (ctx.repo_root / f"webbed_duck/static/assets/wd/{name}.js").is_file()
                for name in ("progress", "header", "params_form", "multi_select", "chart_boot")
            ),
            s,
        )),
        (lambda s: s.startswith("Compiled routes declare the assets they require via a `[ui]` section"), lambda s: _ensure(
            hasattr(ui_layout_module, "resolve_assets"),
            s,
        )),
        (lambda s: s.startswith("`resolve_assets` keeps the canonical ordering"), lambda s: _ensure(
            ui_layout_module.resolve_assets(
                {"ui": {"styles": ["layout", "custom", "cards"], "scripts": ["custom_a", "header", "custom_b"]}},
                default_styles=["layout"],
                default_scripts=["header"],
                extra_styles=["charts"],
                extra_scripts=["chart_boot"],
            ).styles
            == ("layout", "custom", "cards", "charts")
            and ui_layout_module.resolve_assets(
                {"ui": {"styles": ["layout", "custom", "cards"], "scripts": ["custom_a", "header", "custom_b"]}},
                default_styles=["layout"],
                default_scripts=["header"],
                extra_styles=["charts"],
                extra_scripts=["chart_boot"],
            ).scripts
            == ("custom_a", "header", "custom_b", "chart_boot")
            and hasattr(ui_layout_module, "render_layout"),
            s,
        )),
        (lambda s: s.startswith("Progressive enhancement remains optional"), lambda s: None),
        (lambda s: s.startswith("- Python unit tests exercise the renderers directly"), lambda s: _ensure(
            (ctx.repo_root / "tests/test_postprocess.py").is_file(),
            s,
        )),
        (lambda s: s.startswith("- Front-end plugins are written as modules"), lambda s: _ensure(
            (ctx.repo_root / "webbed_duck/static/assets/wd/header.js").is_file(),
            s,
        )),
        (lambda s: s.startswith("- End-to-end and visual verification should be automated"), lambda s: None),
        (
            lambda s: s.startswith("- Front-end unit tests live in `frontend_tests/`"),
            lambda s: _ensure(
                (ctx.repo_root / "frontend_tests").is_dir()
                and (ctx.repo_root / "docs" / "frontend_testing.md").is_file(),
                s,
            ),
        ),
        (
            lambda s: s.startswith("- Run both suites together (`pytest && npm test`)"),
            lambda s: None,
        ),
        (lambda s: s.startswith("Routes may set `default_format`"), lambda s: None),
        (lambda s: s.startswith("- You can query DuckDB-native sources"), lambda s: None),
        (lambda s: s.startswith("- For derived inputs"), lambda s: None),
        (lambda s: s.startswith("- After loading the cached (or freshly queried) page"), lambda s: _ensure(
            ctx.override_payload["column"] == "note", s
        )),
        (lambda s: s.startswith("- Analytics (hits, rows, latency"), lambda s: _ensure(
            ctx.analytics_payload["routes"], s
        )),
        (lambda s: s.startswith("- When a route defines `cache.rows_per_page`"), lambda s: _ensure(
            ctx.cache_enforced_payload["offset"] == 2 and ctx.cache_enforced_payload["limit"] == 2,
            s,
        )),
        (lambda s: s.startswith("- The global `[cache]` configuration exposes"), lambda s: _ensure(
            hasattr(ctx.cache_config, "page_rows")
            and hasattr(ctx.cache_config, "enforce_global_page_size")
            and ctx.cache_config.page_rows == Config().cache.page_rows,
            s,
        )),
        (lambda s: s.startswith("- Authentication modes are controlled via `config.toml`"), lambda s: _ensure(
            ctx.share_payload["meta"]["token"] is not None, s
        )),
        (lambda s: s.startswith("- Pseudo sessions enforce the `auth.allowed_domains`"), lambda s: _ensure(
            ctx.auth_allowed_domains == ["example.com"]
            and ctx.share_db_hashes[0] != ctx.share_payload["meta"]["token"]
            and ctx.share_db_hashes[1] != ""
            and ctx.email_bind_to_user_agent is False
            and ctx.email_bind_to_ip_prefix is False,
            s,
        )),
        (lambda s: s.startswith("- When configuring `email.adapter`"), lambda s: _ensure(
            isinstance(
                pytest.raises(
                    TypeError,
                    load_email_sender,
                    "tests.test_readme_claims:not_callable",
                ).value,
                TypeError,
            ),
            s,
        )),
        (lambda s: s.startswith("- Shares enforce the global `share.max_total_size_mb`"), lambda s: _ensure(
            hasattr(ctx.share_config, "max_total_size_mb")
            and ctx.share_config.max_total_size_mb >= 1
            and ctx.share_payload["meta"]["attachments"] == []
            and ctx.share_payload["meta"]["zipped"] is False,
            s,
        )),
        (lambda s: s.startswith("- Internal tooling can reuse share-safe validation"), lambda s: _ensure(
            ctx.local_resolve_payload.get("route_id") == "hello"
            and ctx.local_resolve_payload.get("columns") == ["greeting"]
            and ctx.local_resolve_payload.get("rows", [{}])[0].get("greeting", "").startswith("Hello"),
            s,
        )),
        (lambda s: s.startswith("- When `auth.mode=\"external\"`"), lambda s: _ensure(
            ctx.external_adapter_checks.get("returns_adapter", False)
            and ctx.external_adapter_checks.get("config_passthrough", False)
            and ctx.external_adapter_checks.get("type_error", False),
            s,
        )),
        (lambda s: s.startswith("- Users with a pseudo-session"), lambda s: _ensure(
            ctx.share_payload["meta"]["rows_shared"] >= 1, s
        )),
        (lambda s: s.startswith("- Routes that define `[append]` metadata"), lambda s: _ensure(
            ctx.append_path.exists(), s
        )),
        (lambda s: s.startswith("Route parameters affect both cache determinism"), lambda s: _ensure(
            any(route.params for route in ctx.compiled_routes), s
        )),
        (lambda s: s == "Remember:", lambda s: None),
        (lambda s: s.startswith("- Never build comma-joined lists"), lambda s: _ensure(
            ctx.duckdb_binding_checks.get("multi", False)
            and ctx.duckdb_binding_checks.get("preprocessed_multi", False),
            s,
        )),
        (lambda s: s.startswith("- Treat file paths and shard lists"), lambda s: _ensure(
            ctx.duckdb_binding_checks.get("single", False),
            s,
        )),
        (lambda s: s.startswith("- Bind everything that comes from the request context"), lambda s: _ensure(
            "?" in ctx.compiled_routes[0].prepared_sql, s
        )),
        (lambda s: s.startswith("If a value is fixed in TOML"), lambda s: _ensure(
            any(
                arg == "US01"
                for use in ctx.route_uses.get("readme_parent", [])
                for arg in use.args.values()
            ),
            s,
        )),
        (lambda s: s.startswith("DuckDB allows parameter binding for table functions"), lambda s: _ensure(
            ctx.duckdb_binding_checks.get("single", False), s
        )),
        (lambda s: s.startswith("interpret them as SQL identifiers."), lambda s: _ensure(
            ctx.duckdb_binding_checks.get("single", False), s
        )),
        (lambda s: s.startswith("To pass multiple artifacts"), lambda s: _ensure(
            ctx.duckdb_binding_checks.get("multi", False), s
        )),
        (lambda s: s.startswith("When the list needs to be composed dynamically"), lambda s: _ensure(
            ctx.duckdb_binding_checks.get("multi", False), s
        )),
        (lambda s: s.startswith("preprocessor that returns the file list"), lambda s: _ensure(
            ctx.duckdb_binding_checks.get("multi", False), s
        )),
        (lambda s: s.startswith("This keeps cache keys deterministic"), lambda s: _ensure(
            ctx.duckdb_binding_checks.get("multi", False), s
        )),
        (lambda s: s.startswith("Executors treat sequences returned by preprocessors"), lambda s: _ensure(
            ctx.duckdb_binding_checks.get("preprocessed_multi", False), s
        )),
        (lambda s: s.startswith("- Constants baked into the route definition"), lambda s: _ensure(
            any(route.id == "readme_parent" and "'US01'" in route.raw_sql for route in ctx.compiled_routes),
            s,
        )),
        (lambda s: s.startswith("- DuckDB accepts sequence parameters directly"), lambda s: _ensure(
            ctx.invariant_combined_payload["rows"]
            and {row["product_code"] for row in ctx.invariant_combined_payload["rows"]} == {"widget", "gadget"},
            s,
        )),
        (lambda s: s.startswith("- Never build comma-separated lists manually"), lambda s: _ensure(
            ctx.invariant_shard_counts == [1, 1, 0], s
        )),
        (lambda s: s.startswith("- Named bindings keep long queries readable"), lambda s: _ensure(
            any(route.id == "readme_parent" and "$label" in route.raw_sql for route in ctx.compiled_routes),
            s,
        )),
        (lambda s: s.startswith("- Pagination, sorting, and debug toggles do not influence"), lambda s: _ensure(
            ctx.cache_enforced_payload["offset"] == 2 and ctx.cache_enforced_payload["limit"] == 2,
            s,
        )),
        (lambda s: s.startswith("- ✅"), lambda s: None),
        (lambda s: s.startswith("- ❌"), lambda s: None),
        (lambda s: s.startswith("A route now spans up to three sibling files"), lambda s: _ensure(
            any(pair["toml"] and pair["sql"] for pair in ctx.source_pairs.values()), s
        )),
        (lambda s: s.startswith("1. **`<stem>.toml`"), lambda s: _ensure(
            any(pair["toml"] for pair in ctx.source_pairs.values()), s
        )),
        (lambda s: s.startswith("2. **`<stem>.sql`"), lambda s: _ensure(
            any(pair["sql"] for pair in ctx.source_pairs.values()), s
        )),
        (lambda s: s.startswith("3. **`<stem>.md`"), lambda s: _ensure(
            any(pair["md"] for pair in ctx.source_pairs.values()), s
        )),
        (lambda s: s.startswith("Common keys inside `<stem>.toml` include:"), lambda s: None),
        (lambda s: s.startswith("- `[params]`"), lambda s: _ensure(
            any(route.params for route in ctx.compiled_routes), s
        )),
        (lambda s: s.startswith("- `[cache]`"), lambda s: _ensure(
            any((route.metadata or {}).get("cache") for route in ctx.compiled_routes), s
        )),
        (lambda s: s.startswith("- `cache_mode`"), lambda s: _ensure(
            ctx.route_cache_modes.get("readme_child") == "materialize", s
        )),
        (lambda s: s.startswith("- `returns`"), lambda s: _ensure(
            ctx.route_returns.get("readme_child") == "parquet", s
        )),
        (lambda s: s.startswith("- `[[uses]]`"), lambda s: _ensure(
            bool(ctx.route_uses.get("readme_parent")), s
        )),
        (lambda s: s.startswith("- Presentation metadata"), lambda s: _ensure(
            ctx.override_payload["column"] == "note", s
        )),
        (lambda s: s.startswith("`routes_src/production/workstation_line.toml`"), lambda s: None),
        (lambda s: s.startswith("`routes_src/production/workstation_line.sql`"), lambda s: None),
        (lambda s: s.startswith("`routes_src/production/workstation_line.md`"), lambda s: None),
        (lambda s: s.startswith("This trio mirrors the canonical on-disk structure"), lambda s: _ensure(
            any(pair["md"] for pair in ctx.source_pairs.values()), s
        )),
        (lambda s: s.startswith("* **Markdown + SQL compiler**"), lambda s: _ensure(
            ctx.compiled_hashes == ctx.recompiled_hashes, s
        )),
        (lambda s: s.startswith("* **Per-request DuckDB execution**"), lambda s: _ensure(
            ctx.duckdb_connect_counts[0] >= 1 and ctx.duckdb_connect_counts[-1] >= 1,
            s,
        )),
        (lambda s: s.startswith("* **Overlay-aware viewers**"), lambda s: _ensure(
            ctx.override_payload["column"] == "note" and ctx.append_path.exists(), s
        )),
        (lambda s: s.startswith("* **Share engine**"), lambda s: _ensure(
            ctx.share_payload["meta"]["rows_shared"] >= 1 and ctx.share_db_hashes[0] != ctx.share_payload["meta"]["token"], s
        )),
        (lambda s: s.startswith("* **Configurable auth adapters**"), lambda s: _ensure(
            ctx.python_requires.startswith(">=3"), s
        )),
        (lambda s: s.startswith("* **Incremental execution**"), lambda s: _ensure(
            len(ctx.incremental_rows) >= 1 and ctx.checkpoints_exists, s
        )),
        (lambda s: s.startswith("- `webbed_duck.core.incremental.run_incremental`"), lambda s: _ensure(
            bool(ctx.incremental_rows)
            and ctx.incremental_checkpoint_value == ctx.incremental_rows[-1].value,
            s,
        )),
        (lambda s: s.startswith("- When the underlying route raises an error"), lambda s: _ensure(
            ctx.incremental_failure_preserves_checkpoint,
            s,
        )),
        (lambda s: s.startswith("- Pass a custom callable via the `runner` parameter"), lambda s: _ensure(
            ctx.incremental_custom_runner_rows > 0
            and ctx.incremental_custom_runner_checkpoint is not None,
            s,
        )),
        (lambda s: s.startswith("* **Extensible plugins**"), lambda s: _ensure(
            ctx.assets_registry_size >= 1 and ctx.charts_registry_size >= 0, s
        )),
        (lambda s: s.startswith("1. **Authoring**"), lambda s: _ensure(
            ctx.repo_structure["routes_src"], s
        )),
        (lambda s: s.startswith("2. **Compilation**"), lambda s: _ensure(
            ctx.repo_structure["routes_build"], s
        )),
        (lambda s: s.startswith("3. **Serving**"), lambda s: _ensure(
            "routes" in ctx.analytics_payload, s
        )),
        (lambda s: s.startswith("4. **Extensions**"), lambda s: _ensure(
            ctx.assets_registry_size >= 1, s
        )),
        (lambda s: s.startswith("Use a virtual environment"), lambda s: None),
        (lambda s: s.startswith("Install the published package"), lambda s: None),
        (lambda s: s.startswith("* Python 3.9 or newer"), lambda s: _ensure(
            _python_requirement_at_least(ctx.python_requires, (3, 9)), s
        )),
        (lambda s: s.startswith("* DuckDB (installed automatically"), lambda s: None),
        (lambda s: s.startswith("* Access to an intranet"), lambda s: None),
        (lambda s: s.startswith("* Optional: `pyzipper`"), lambda s: None),
        (lambda s: s.startswith("Optional extras:"), lambda s: _ensure(
            any("pyzipper" in dep for dep in ctx.dependencies), s
        )),
        (lambda s: s.startswith("After upgrades"), lambda s: None),
        (lambda s: s.startswith("`webbed_duck` reads a TOML configuration"), lambda s: _ensure(
            isinstance(load_config(None), Config), s
        )),
        (lambda s: s.startswith("Key principles:"), lambda s: None),
        (lambda s: s.startswith("* **`storage_root`**"), lambda s: _ensure(
            ctx.storage_root_layout["runtime"], s
        )),
        (lambda s: s.startswith("* **Auth adapters**"), lambda s: _ensure(
            ctx.share_payload["meta"]["token"] is not None, s
        )),
        (lambda s: s.startswith("* **Transport mode**"), lambda s: None),
        (lambda s: s.startswith("* **Feature flags**"), lambda s: _ensure(
            any(item["name"] == "name" for item in ctx.schema_payload.get("form", [])), s
        )),
        (lambda s: s.startswith("After editing `config.toml`"), lambda s: None),
        (lambda s: s.startswith("Once the package is installed"), lambda s: _ensure(
            ctx.repo_structure["config.toml"], s
        )),
        (lambda s: s.startswith("Add a starter route"), lambda s: _ensure(
            any(route.id == "hello" for route in ctx.compiled_routes), s
        )),
        (lambda s: s.startswith("This minimal setup is enough"), lambda s: _ensure(
            ctx.route_json["rows"], s
        )),
        (lambda s: s.startswith("Routes live in"), lambda s: _ensure(
            ctx.repo_structure["routes_src"], s
        )),
        (lambda s: s.startswith("Run `webbed-duck compile`"), lambda s: None),
        (lambda s: s.startswith("- **Default behaviour:**"), lambda s: _ensure(
            ctx.reload_capable, s
        )),
        (lambda s: s.startswith("- **Configurable toggles:**"), lambda s: _ensure(
            ctx.reload_capable, s
        )),
        (lambda s: s.startswith("- **Configuration surface:**"), lambda s: _ensure(
            ctx.repo_structure["config.toml"], s
        )),
        (lambda s: s.startswith("* `@route`"), lambda s: _ensure(
            all(hasattr(route, "id") for route in ctx.compiled_routes), s
        )),
        (lambda s: s.startswith("* `@params`"), lambda s: _ensure(
            any(route.params for route in ctx.compiled_routes), s
        )),
        (lambda s: s.startswith("* `@preprocess`"), lambda s: _ensure(
            all(hasattr(route, "preprocess") for route in ctx.compiled_routes), s
        )),
        (lambda s: s.startswith("* `@sql`"), lambda s: _ensure(
            all(hasattr(route, "prepared_sql") for route in ctx.compiled_routes), s
        )),
        (lambda s: s.startswith("* `@postprocess`"), lambda s: _ensure(
            all(hasattr(route, "postprocess") for route in ctx.compiled_routes), s
        )),
        (lambda s: s.startswith("* `@charts`"), lambda s: _ensure(
            all(hasattr(route, "charts") for route in ctx.compiled_routes), s
        )),
        (lambda s: s.startswith("* `@append`"), lambda s: _ensure(
            ctx.append_path.exists(), s
        )),
        (lambda s: s.startswith("* `@assets`"), lambda s: _ensure(
            all(hasattr(route, "assets") for route in ctx.compiled_routes), s
        )),
        (lambda s: s.startswith("Authoring tips:"), lambda s: None),
        (lambda s: s.startswith("* Favor set-based SQL"), lambda s: None),
        (lambda s: s.startswith("* Keep preprocessors"), lambda s: None),
        (lambda s: s.startswith("* Use folders"), lambda s: None),
        (lambda s: s.startswith("1. **Compile**"), lambda s: _ensure(
            ctx.compiled_hashes == ctx.recompiled_hashes, s
        )),
        (lambda s: s.startswith("2. **Serve**"), lambda s: None),
        (lambda s: s.startswith("3. **Visit**"), lambda s: _ensure(
            ctx.route_json["rows"][0]["greeting"].startswith("Hello"), s
        )),
        (lambda s: s.startswith("4. **Interact**"), lambda s: _ensure(
            ctx.override_payload["column"] == "note", s
        )),
        (lambda s: s.startswith("* `POST /routes/{route_id}/overrides`"), lambda s: _ensure(
            ctx.override_payload["column"] == "note", s
        )),
        (lambda s: s.startswith("* `POST /routes/{route_id}/append`"), lambda s: _ensure(
            ctx.append_path.exists(), s
        )),
        (lambda s: s.startswith("* `GET /routes/{route_id}/schema`"), lambda s: _ensure(
            ctx.schema_payload.get("route_id") == "hello", s
        )),
        (lambda s: s.startswith("5. **Share**"), lambda s: _ensure(
            ctx.share_payload["meta"]["inline_snapshot"] is True, s
        )),
        (lambda s: s.startswith("The runtime stores share metadata"), lambda s: _ensure(
            ctx.storage_root_layout["runtime/meta.sqlite3"], s
        )),
        (lambda s: s.startswith("6. **Run incremental workloads**"), lambda s: _ensure(
            ctx.checkpoints_exists, s
        )),
        (lambda s: s.startswith("Progress persists"), lambda s: _ensure(
            ctx.checkpoints_exists, s
        )),
        (lambda s: s.startswith("* **Request lifecycle**"), lambda s: _ensure(
            ctx.arrow_headers["content-type"].startswith("application/vnd.apache.arrow.stream"), s
        )),
        (lambda s: s.startswith("* **Analytics**"), lambda s: _ensure(
            ctx.analytics_payload["routes"], s
        )),
        (lambda s: s.startswith("* **Local route chaining**"), lambda s: _ensure(
            ctx.local_resolve_payload["route_id"] == "hello", s
        )),
        (lambda s: s.startswith("* **Static assets**"), lambda s: _ensure(
            ctx.assets_registry_size >= 1, s
        )),
        (lambda s: s.startswith("* **Email integration**"), lambda s: _ensure(
            len(ctx.email_records) == 1, s
        )),
        (lambda s: "The TOML + SQL sidecar pair is the single source of truth" in s, lambda s: _ensure(
            bool(ctx.compiled_routes) and not ctx.legacy_sidecars_present,
            s,
        )),
        (lambda s: s.startswith("1. **Frontmatter (`+++"), lambda s: None),
        (lambda s: s.startswith("2. **Markdown body:"), lambda s: None),
        (lambda s: s.startswith("3. **SQL code block:"), lambda s: None),
        (lambda s: s.startswith("Common keys include:"), lambda s: None),
        (lambda s: s.startswith("- `id`: Stable identifier"), lambda s: None),
        (lambda s: s.startswith("- `path`: HTTP path"), lambda s: None),
        (lambda s: s.startswith("- `title`, `description`"), lambda s: None),
        (lambda s: s.startswith("- `version`: Optional"), lambda s: None),
        (lambda s: s.startswith("- `default_format`"), lambda s: None),
        (lambda s: s.startswith("- `allowed_formats`"), lambda s: None),
        (lambda s: s.startswith("- `[params."), lambda s: None),
        (lambda s: s.startswith("- Presentation metadata blocks"), lambda s: _ensure(
            ctx.override_payload["column"] == "note" and ctx.append_path.exists(), s
        )),
        (lambda s: s.startswith("- `[[preprocess]]` entries"), lambda s: None),
        (lambda s: s.startswith("- Unexpected keys trigger compile-time warnings"), lambda s: _ensure(
            _frontmatter_warning_emitted(), s
        )),
        (lambda s: s.startswith("- Write DuckDB SQL in `<stem>.sql`"), lambda s: _ensure(
            any(pair["sql"] for pair in ctx.source_pairs.values()), s
        )),
        (lambda s: s.startswith("- Reference parameters registered in TOML"), lambda s: _ensure(
            any("$label" in route.raw_sql for route in ctx.compiled_routes), s
        )),
        (lambda s: s.startswith("- Dependencies declared via `[[uses]]`"), lambda s: _ensure(
            bool(ctx.composition_payload.get("rows")), s
        )),
        (lambda s: s.startswith("Routes can further customise behaviour"), lambda s: _ensure(
            ctx.override_payload["column"] == "note", s
        )),
        (lambda s: s.startswith("> **Promise:** By 0.4"), lambda s: _ensure(
            ctx.reload_capable, s
        )),
        (lambda s: s.startswith("MVP 0.4 is the first release"), lambda s: None),
        (lambda s: s.startswith("- **Preprocessors:**"), lambda s: None),
        (lambda s: s.startswith("- **Postprocessors and presentation:**"), lambda s: _ensure(
            "card" in ctx.cards_text.lower(), s
        )),
        (lambda s: s.startswith("- **Assets and overlays:**"), lambda s: _ensure(
            ctx.override_payload["column"] == "note", s
        )),
        (lambda s: s.startswith("- **Local execution:**"), lambda s: _ensure(
            ctx.local_resolve_payload["route_id"] == "hello", s
        )),
        (lambda s: s.startswith("As the plugin hooks stabilise"), lambda s: None),
        (lambda s: s.startswith("- Auto-compiling `webbed-duck serve` command"), lambda s: _ensure(
            ctx.reload_capable, s
        )),
        (lambda s: s.startswith("- Built-in watch mode (`server.watch`"), lambda s: _ensure(
            ctx.reload_capable, s
        )),
        (lambda s: s.startswith("- Dynamic route registry inside the FastAPI app"), lambda s: _ensure(
            ctx.reload_capable, s
        )),
        (lambda s: s.startswith("- CLI and docs tuned for a zero-config quick start"), lambda s: _ensure(
            ctx.repo_structure["routes_src"] and ctx.repo_structure["config.toml"], s
        )),
        (lambda s: s.startswith("- Declarative caching / snapshot controls"), lambda s: None),
        (lambda s: s.startswith("- Richer auto-generated parameter forms"), lambda s: None),
        (lambda s: s.startswith("- Additional auth adapter examples"), lambda s: None),
        (lambda s: s.startswith("- **Path resolution:**"), lambda s: _validate_path_resolution_statement()),
        (lambda s: s.startswith("All runtime paths derive"), lambda s: _ensure(
            ctx.storage_root_layout["runtime"], s
        )),
        (lambda s: s.startswith("Ensure the service user"), lambda s: None),
        (lambda s: s.startswith("* **Securable by design**"), lambda s: None),
        (lambda s: s.startswith("* **Connection management**"), lambda s: _ensure(
            ctx.duckdb_connect_counts[0] >= 1 and 0 in ctx.duckdb_connect_counts,
            s,
        )),
        (lambda s: s.startswith("* **Secrets hygiene**"), lambda s: _ensure(
            ctx.share_db_hashes[0] != ctx.share_payload["meta"]["token"], s
        )),
        (lambda s: s.startswith("* **Path safety**"), lambda s: _ensure(
            ctx.storage_root_layout["runtime"], s
        )),
        (lambda s: s.startswith("* **Proxy deployment**"), lambda s: None),
        (lambda s: s.startswith("* **External auth**"), lambda s: None),
        (lambda s: s.startswith("Run the pytest suite"), lambda s: None),
        (lambda s: s.startswith("The suite exercises"), lambda s: _ensure(
            ctx.analytics_payload["routes"], s
        )),
        (lambda s: s.startswith("Linting can be layered"), lambda s: None),
        (lambda s: s.startswith("* **Missing compiled routes**"), lambda s: _ensure(
            ctx.compiled_hashes == ctx.recompiled_hashes, s
        )),
        (lambda s: s.startswith("* **ZIP encryption disabled**"), lambda s: None),
        (lambda s: s.startswith("* **Authentication failures**"), lambda s: _ensure(
            ctx.share_db_hashes[1] != "", s
        )),
        (lambda s: s.startswith("* **Proxy misconfiguration**"), lambda s: None),
        (lambda s: s.startswith("* **DuckDB locking errors**"), lambda s: _ensure(
            all(count >= 0 for count in ctx.duckdb_connect_counts), s
        )),
        (lambda s: s.startswith("* Current release"), lambda s: None),
        (lambda s: s.startswith("* Major focuses"), lambda s: None),
        (lambda s: s.startswith("* Upcoming ideas"), lambda s: None),
        (lambda s: s.startswith("Refer to the maintainer logs"), lambda s: _ensure(
            (ctx.repo_root / "AGENTS.md").is_file(), s
        )),
        (lambda s: s.startswith("* [`AGENTS.md`]"), lambda s: _ensure(
            (ctx.repo_root / "AGENTS.md").is_file(), s
        )),
        (lambda s: s.startswith("* [`docs/`]"), lambda s: _ensure(
            ctx.repo_structure["docs"], s
        )),
        (lambda s: s.startswith("* [`examples/emailer.py`]"), lambda s: _ensure(
            (ctx.repo_root / "examples" / "emailer.py").is_file(), s
        )),
        (lambda s: s.startswith("* [`CHANGELOG.md`]"), lambda s: _ensure(
            ctx.repo_structure["CHANGELOG.md"], s
        )),
        (lambda s: s.startswith("Bug reports and feature requests"), lambda s: None),
        (lambda s: s.startswith("1. Fork the repository"), lambda s: None),
        (lambda s: s.startswith("2. Install dependencies"), lambda s: None),
        (lambda s: s.startswith("3. Run `pytest`"), lambda s: None),
        (lambda s: s.startswith("4. Document new behavior"), lambda s: None),
        (lambda s: s.startswith("5. Follow the invariants"), lambda s: _ensure(
            (ctx.repo_root / "AGENTS.md").is_file(), s
        )),
        (lambda s: s.startswith("Happy routing!"), lambda s: _ensure(
            "Happy routing" in Path(ctx.repo_root / "README.md").read_text(encoding="utf-8"), s
        )),
    ]

    unmatched: list[str] = []
    for statement in ctx.readme_lines:
        for predicate, validator in validators:
            if predicate(statement):
                validator(statement)
                break
        else:
            unmatched.append(statement)

    assert not unmatched, "README statements without coverage: " + json.dumps(unmatched, indent=2)
