# Filesystem-based preprocess callable demo

This walkthrough demonstrates pointing a preprocessor at a Python file without
installing it as a package. The compiler normalises the file reference and
verifies that the named callable exists during `webbed-duck compile`.

## Plugin source

```python
# demos/preprocess-path-callable/plugins/custom_stamp.py
from __future__ import annotations

from typing import Mapping

from webbed_duck.server.preprocess import PreprocessContext


def derive_tag(
    params: Mapping[str, object], *, context: PreprocessContext, prefix: str = "path"
) -> Mapping[str, object]:
    result = dict(params)
    base = str(result.get("name", "")) or "anonymous"
    result["tag"] = f"{prefix}-{base}"
    return result
```

## Route metadata

```toml
[[preprocess]]
callable_path = "demos/preprocess-path-callable/plugins/custom_stamp.py"
callable_name = "derive_tag"
prefix = "local"
```

## Runtime check

```
$ python - <<'PY'
from webbed_duck.core.routes import RouteDefinition
from webbed_duck.server.preprocess import run_preprocessors

route = RouteDefinition(
    id="demo",
    path="/demo",
    methods=["GET"],
    raw_sql="SELECT 1",
    prepared_sql="SELECT 1",
    param_order=[],
    params=(),
    metadata={},
)

steps = [
    {
        "callable_path": "demos/preprocess-path-callable/plugins/custom_stamp.py",
        "callable_name": "derive_tag",
        "prefix": "local",
    }
]

result = run_preprocessors(steps, {"name": "Ada"}, route=route, request=None)
print(result)
PY
{'name': 'Ada', 'tag': 'local-Ada'}
```
