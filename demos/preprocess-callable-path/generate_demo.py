from __future__ import annotations

import datetime as _dt
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.preprocess import run_preprocessors


TEMPLATE = """<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->
# Preprocess callable (path) demo

Generated on {timestamp} UTC.

This demo creates an isolated plugin file, references it via `callable_path` in a
route TOML, and shows the compiled metadata plus the transformed parameters.

## Command Transcript

### 1. Compile routes

**Command**

```python
compile_routes(SRC_DIR, BUILD_DIR)
```

**Response JSON**

```json
{compile_payload}
```

### 2. Compiled preprocess metadata

```json
{step_payload}
```

### 3. Preprocess execution

**Input params**

```json
{input_payload}
```

**Output params**

```json
{output_payload}
```
"""


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir(parents=True)
        plugin_file = plugins_dir / "path_helper.py"
        plugin_file.write_text(
            """
from __future__ import annotations

from typing import Mapping


def add_suffix(params: Mapping[str, object], *, suffix: str) -> Mapping[str, object]:
    result = dict(params)
    result["name"] = f"{result.get('name', '')}{suffix}"
    return result
""".strip()
            + "\n",
            encoding="utf-8",
        )

        src_dir = tmp_path / "routes_src"
        build_dir = tmp_path / "routes_build"
        src_dir.mkdir()

        (src_dir / "demo.toml").write_text(
            """
id = "path_demo"
path = "/path_demo"

[params.name]
type = "str"

[[preprocess]]
callable_path = "../plugins/path_helper.py"
callable_name = "add_suffix"
suffix = "!"
""".strip()
            + "\n",
            encoding="utf-8",
        )
        (src_dir / "demo.sql").write_text("SELECT {{name}} AS name;\n", encoding="utf-8")

        compile_routes(src_dir, build_dir)
        routes = load_compiled_routes(build_dir)
        route = next(defn for defn in routes if defn.id == "path_demo")
        step = dict(route.preprocess[0])

        input_params = {"name": "duck"}
        output_params = run_preprocessors([step], input_params, route=route, request=None)

        doc = TEMPLATE.format(
            timestamp=_dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
            compile_payload=json.dumps(
                {"compiled_route_ids": [defn.id for defn in routes]}, indent=2
            ),
            step_payload=json.dumps(step, indent=2, sort_keys=True),
            input_payload=json.dumps(input_params, indent=2, sort_keys=True),
            output_payload=json.dumps(output_params, indent=2, sort_keys=True),
        )

    demo_path = Path(__file__).with_name("demo.md")
    demo_path.write_text(doc, encoding="utf-8")


if __name__ == "__main__":
    main()
