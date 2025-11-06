# Configured plugins directory demo

This walkthrough shows how to point `[[preprocess]]` entries at a plugin file that
ships alongside your application. All plugin code now lives under the configured
`server.plugins_dir`, so there is no need to install packages or adjust
`PYTHONPATH`.

## Plugin source

```python
# web/plugins/stamp_label.py
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
callable_path = "stamp_label.py"
callable_name = "stamp_label"
kwargs = { label = "plugins-demo" }
```

## Runtime check

```
$ python - <<'PY'
from webbed_duck.core.routes import RouteDefinition
from webbed_duck.plugins.loader import PluginLoader
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
        "callable_path": "stamp_label.py",
        "callable_name": "stamp_label",
        "kwargs": {"label": "plugins-demo"},
    }
]

loader = PluginLoader("web/plugins")
result = run_preprocessors(
    steps,
    {"name": "Ada"},
    route=route,
    request=None,
    loader=loader,
)
print(result)
PY
{'name': 'Ada', 'label': 'plugins-demo'}
```
