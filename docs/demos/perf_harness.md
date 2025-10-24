# Performance Harness

The `perf` sub-command included with `webbed_duck` exercises a compiled route
repeatedly and prints summary timing statistics. It is intended for local
capacity planning and regression detection without needing to stand up the HTTP
service.

```bash
$ webbed-duck perf hello_world --build routes_build --iterations 10 --param name=duck
Route: hello_world
Iterations: 10
Rows (last run): 1
Average latency: 3.412 ms
95th percentile latency: 3.981 ms
```

Parameters can be supplied multiple times via `--param`. The harness executes
routes in-process using the same DuckDB execution path as the HTTP server while
respecting overrides stored in `storage_root/runtime`.
