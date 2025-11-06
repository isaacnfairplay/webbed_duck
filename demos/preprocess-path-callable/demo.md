<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->
# Preprocess Path Reference Demo

Generated on 2025-11-06T00:07:42.699126+00:00.

## 1. Compile the demo route

```python
compile_routes(ROUTE_SOURCE, BUILD_DIR)
```

**Result**

- routes_compiled: 1
- build_dir: /workspace/webbed_duck/demos/preprocess-path-callable/_workspace/routes_build

## 2. Execute the route via LocalRouteRunner

```python
runner.run("path_preprocess_demo", params={"name": "otter"}, format="records")
```

**Response JSON**

```json
[
  {
    "greeting": "hi otter",
    "name": "otter",
    "run_date": "2025-11-06"
  }
]
```

The `greeting` and `run_date` values originate from the file-backed preprocessor referenced via `callable_path`.
