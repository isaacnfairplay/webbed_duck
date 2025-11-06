from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = DEMO_DIR / "_workspace"
BUILD_DIR = WORKSPACE_DIR / "routes_build"
STORAGE_DIR = WORKSPACE_DIR / "storage"
DEMO_PATH = DEMO_DIR / "demo.md"
ROUTE_SOURCE = DEMO_DIR / "routes_src"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from webbed_duck.config import Config  # noqa: E402
from webbed_duck.core.compiler import compile_routes  # noqa: E402
from webbed_duck.core.local import LocalRouteRunner  # noqa: E402


def _reset_workspace() -> None:
    if WORKSPACE_DIR.exists():
        shutil.rmtree(WORKSPACE_DIR)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def _render_markdown(routes_compiled: int, records: list[dict[str, object]], *, generated_at: datetime) -> str:
    lines: list[str] = []
    lines.append("<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->")
    lines.append("# Preprocess Path Reference Demo")
    lines.append("")
    lines.append(f"Generated on {generated_at.isoformat()}.")
    lines.append("")
    lines.append("## 1. Compile the demo route")
    lines.append("")
    lines.append("```python")
    lines.append("compile_routes(ROUTE_SOURCE, BUILD_DIR)")
    lines.append("```")
    lines.append("")
    lines.append("**Result**")
    lines.append("")
    lines.append(f"- routes_compiled: {routes_compiled}")
    lines.append(f"- build_dir: {BUILD_DIR}")
    lines.append("")
    lines.append("## 2. Execute the route via LocalRouteRunner")
    lines.append("")
    lines.append("```python")
    lines.append(
        "runner.run(\"path_preprocess_demo\", params={\"name\": \"otter\"}, format=\"records\")"
    )
    lines.append("```")
    lines.append("")
    lines.append("**Response JSON**")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(records, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append(
        "The `greeting` and `run_date` values originate from the file-backed preprocessor referenced via `callable_path`."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    generated_at = datetime.now(tz=timezone.utc)
    _reset_workspace()

    config = Config()
    config.server.build_dir = BUILD_DIR
    config.server.source_dir = ROUTE_SOURCE
    config.server.storage_root = STORAGE_DIR

    original_cwd = Path.cwd()
    try:
        os.chdir(REPO_ROOT)
        routes = compile_routes(ROUTE_SOURCE, BUILD_DIR)
        runner = LocalRouteRunner(routes=routes, build_dir=BUILD_DIR, config=config)
        records = runner.run(
            "path_preprocess_demo",
            params={"name": "otter"},
            format="records",
        )
    finally:
        os.chdir(original_cwd)
    assert isinstance(records, list)

    DEMO_PATH.write_text(
        _render_markdown(len(routes), records, generated_at=generated_at),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
