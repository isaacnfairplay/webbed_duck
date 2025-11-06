<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->
# Preprocess Module Reference Demo

Generated on 2025-11-06T00:06:30.574068+00:00.

## 1. Compile the demo route

```python
compile_routes(ROUTE_SOURCE, BUILD_DIR)
```

**Result**

- routes_compiled: 1
- build_dir: /workspace/webbed_duck/demos/preprocess-module-callable/_workspace/routes_build

## 2. Execute the route via LocalRouteRunner

```python
runner.run("module_preprocess_demo", params={"name": "sparrow"}, format="records")
```

**Response JSON**

```json
[
  {
    "generated_at": "2025-11-06T00:06:30",
    "greeting": "module-demo:sparrow",
    "name": "sparrow"
  }
]
```

The `greeting` and `generated_at` fields are injected by the module-backed preprocessor.
