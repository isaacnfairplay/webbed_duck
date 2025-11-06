<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->
# Preprocess callable (path) demo

Generated on 2025-11-06T00:01:58+00:00 UTC.

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
{
  "compiled_route_ids": [
    "path_demo"
  ]
}
```

### 2. Compiled preprocess metadata

```json
{
  "callable_name": "add_suffix",
  "callable_path": "../plugins/path_helper.py",
  "callable_resolved_path": "/tmp/tmp5w14241q/plugins/path_helper.py",
  "callable_source": "../plugins/path_helper.py",
  "callable_source_type": "path",
  "suffix": "!"
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
  "name": "duck!"
}
```
