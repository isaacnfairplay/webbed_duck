# Module-based preprocess callable demo

This walkthrough shows how to point `[[preprocess]]` entries at a module that lives
inside your application package. The compiler resolves the callable during
`webbed-duck compile`, so the server never hits a missing-import error at runtime.

## Plugin source

```python
# webbed_duck/demos/preprocess_plugins.py
from __future__ import annotations

from typing import Mapping

from webbed_duck.server.preprocess import PreprocessContext


def stamp_label(
    params: Mapping[str, object], *, context: PreprocessContext, label: str = "demo"
) -> Mapping[str, object]:
    result = dict(params)
    result["label"] = label
    return result
```

## Route metadata

```toml
[[preprocess]]
callable_module = "webbed_duck.demos.preprocess_plugins"
callable_name = "stamp_label"
label = "module-demo"
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
        "callable_module": "webbed_duck.demos.preprocess_plugins",
        "callable_name": "stamp_label",
        "label": "module-demo",
    }
]

result = run_preprocessors(steps, {"name": "Ada"}, route=route, request=None)
print(result)
PY
{'name': 'Ada', 'label': 'module-demo'}
```
