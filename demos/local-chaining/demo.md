<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->
# Local Route Chaining Demo

Generated on 2025-11-04T02:50:03.863737+00:00 UTC.

## Feature & Auth Toggles

These toggles were applied during the run and restored afterwards:

- **auth.mode**: "none" → "pseudo"
- **feature_flags.overrides_enabled**: false → true

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
    "hello_world"
  ]
}
```

### 2. LocalRouteRunner first execution

**Command**

```python
runner.run(route_id="hello_world", params={"name": "Ada"}, format="records")
```

**Response JSON**

```json
{
  "rows": [
    {
      "created_at": "2025-11-04T02:50:03.648680+00:00",
      "greeting": "Hello, Ada!",
      "greeting_length": 11,
      "note": "Personalized greeting rendered by DuckDB"
    }
  ]
}
```

**Notes**

- used_cache: True
- cache_hit: False
- total_rows: 1
- applied_offset: 0
- applied_limit: None

### 3. LocalRouteRunner cached execution

**Command**

```python
runner.run(route_id="hello_world", params={"name": "Ada"}, format="records")
```

**Response JSON**

```json
{
  "rows": [
    {
      "created_at": "2025-11-04T02:50:03.648680+00:00",
      "greeting": "Hello, Ada!",
      "greeting_length": 11,
      "note": "Personalized greeting rendered by DuckDB"
    }
  ]
}
```

**Notes**

- used_cache: True
- cache_hit: True
- total_rows: 1
- applied_offset: 0
- applied_limit: None

### 4. run_route baseline

**Command**

```python
run_route("hello_world", {"name": "Ada"}, routes=routes, config=config, format="records")
```

**Response JSON**

```json
{
  "rows": [
    {
      "created_at": "2025-11-04T02:50:03.648680+00:00",
      "greeting": "Hello, Ada!",
      "greeting_length": 11,
      "note": "Personalized greeting rendered by DuckDB"
    }
  ]
}
```

### 5. LocalRouteRunner error path

**Command**

```python
runner.run(route_id="missing_route")
```

**Error**

```text
'missing_route'
```

### 6. Overlay override applied

**Command**

```python
overlay_store.upsert(route_id="hello_world", row_key=row_key, column="note", value="Override injected by demo", reason="Demo override", author="demo")
```

**Response JSON**

```json
{
  "author_hash": "2a97516c354b68848cdbd8f54a226a0a55b21ed138e207ad6c5cbb9c00aa5aea",
  "author_user_id": null,
  "column": "note",
  "created_ts": 1762224603.698558,
  "reason": "Demo override",
  "route_id": "hello_world",
  "row_key": "{\"greeting\": \"Hello, Ada!\"}",
  "value": "Override injected by demo"
}
```

### 7. LocalRouteRunner after override

**Command**

```python
runner.run(route_id="hello_world", params={"name": "Ada"}, format="records")
```

**Response JSON**

```json
{
  "rows": [
    {
      "created_at": "2025-11-04T02:50:03.648680+00:00",
      "greeting": "Hello, Ada!",
      "greeting_length": 11,
      "note": "Override injected by demo"
    }
  ]
}
```

**Notes**

- used_cache: True
- cache_hit: True
- total_rows: 1
- applied_offset: 0
- applied_limit: None

### 8. HTTP /local/resolve

**Command**

```python
client.post("/local/resolve", json=http_payload)
```

**Request JSON**

```json
{
  "format": "json",
  "params": {
    "name": "Ada"
  },
  "record_analytics": true,
  "reference": "local:hello_world?column=greeting&column=note"
}
```

**Response JSON**

```json
{
  "charts": [
    {
      "html": "<svg viewBox='0 0 400 160'><text x='8' y='80'>Unknown y column: greeting_length</text></svg>",
      "id": "greeting_length"
    }
  ],
  "columns": [
    "greeting",
    "note"
  ],
  "description": "Return a greeting using DuckDB",
  "elapsed_ms": 3.583,
  "limit": null,
  "offset": 0,
  "route_id": "hello_world",
  "row_count": 1,
  "rows": [
    {
      "greeting": "Hello, Ada!",
      "note": "Override injected by demo"
    }
  ],
  "title": "Hello world",
  "total_rows": 1
}
```

**Notes**

- status_code: 200

### 9. HTTP /local/resolve error

**Command**

```python
client.post("/local/resolve", json={})
```

**Request JSON**

```json
{}
```

**Response JSON**

```json
{
  "detail": {
    "category": "ValidationError",
    "code": "missing_parameter",
    "hint": "Ensure the query string includes the documented parameter name.",
    "message": "reference is required"
  }
}
```

**Notes**

- status_code: 400
