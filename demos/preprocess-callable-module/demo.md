<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->
# Preprocess callable (module) demo

Generated on 2025-11-06T00:02:16+00:00 UTC.

This demo exposes a helper via `callable_module`, verifies the compiler loads it,
and shows the resulting parameter payload.

## Command Transcript

### 1. Compile routes

**Command**

```python
compile_routes(SRC_DIR, BUILD_DIR)
```

**Response JSON**

```json
{
  "compiled_route_ids": [
    "module_demo"
  ]
}
```

### 2. Compiled preprocess metadata

```json
{
  "callable_module": "module_demo_pkg.helpers",
  "callable_name": "add_prefix",
  "callable_resolved_path": "/tmp/tmp2muaegnp/module_demo_pkg/helpers.py",
  "callable_source": "module_demo_pkg.helpers",
  "callable_source_type": "module",
  "prefix": "pre-"
}
```

### 3. Preprocess execution

**Input params**

```json
{
  "name": "duck"
}
```

**Output params**

```json
{
  "name": "pre-duck"
}
```
