from pathlib import Path

from examples.perf_harness import benchmark_route
from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes

ROUTE = """
+++
id = "perf"
path = "/perf"
+++

```sql
SELECT 42 AS answer;
```
"""


def test_benchmark_route(tmp_path: Path) -> None:
    src = tmp_path / "src"
    build = tmp_path / "build"
    src.mkdir()
    (src / "perf.sql.md").write_text(ROUTE, encoding="utf-8")
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    stats = benchmark_route("perf", iterations=3, routes=routes, config=config, params={})
    assert stats["route_id"] == "perf"
    assert stats["iterations"] == 3
    assert stats["row_count"] == 1
    assert stats["total_ms"] >= 0
    assert stats["avg_ms"] >= 0
