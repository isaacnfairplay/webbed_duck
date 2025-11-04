<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->
# Fix-and-Forward Demo

This walkthrough shows how overrides, append logging, local references, and shares work together once you start fixing data and immediately forwarding the result.

Generated on 2025-11-04T05:01:33.593046+00:00 UTC.

## Feature & Auth Toggles

These toggles were applied during the run and restored afterwards:

- **auth.mode**: "none" → "pseudo"
- **feature_flags.overrides_enabled**: false → true

## Command Transcript

### 1. Compile demo routes

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

### 2. Establish pseudo-auth session

**Command**

```python
client.post("/auth/pseudo/session", json={"email": "ops.lead@example.com"})
```

**Request JSON**

```json
{
  "email": "ops.lead@example.com"
}
```

**Response JSON**

```json
{
  "user": {
    "email_hash": "fc2cb80df0f2bb8cf4885ab6e40623907b6a0b85750691f991e7aff1fdbc3aab",
    "expires_at": "2025-11-04T05:46:33.429592+00:00",
    "id": "ops.lead@example.com"
  }
}
```

**Notes**

- status_code: 200
- content_type: application/json

### 3. Baseline hello route response

**Command**

```python
client.get("/hello", params={"name": "River", "format": "json"})
```

**Query Parameters**

```json
{
  "format": "json",
  "name": "River"
}
```

**Response JSON**

```json
{
  "charts": [
    {
      "html": "<svg viewBox='0 0 400 160' role='img' aria-label='Line chart'><polyline fill='none' stroke='#3b82f6' stroke-width='2' points='12.0,80.0'/></svg>",
      "id": "greeting_length"
    }
  ],
  "columns": [
    "greeting",
    "note",
    "greeting_length",
    "created_at"
  ],
  "description": "Return a greeting using DuckDB",
  "elapsed_ms": 94.916,
  "limit": null,
  "offset": 0,
  "route_id": "hello_world",
  "row_count": 1,
  "rows": [
    {
      "created_at": "2025-11-04T05:01:33.481496+00:00",
      "greeting": "Hello, River!",
      "greeting_length": 13,
      "note": "Personalized greeting rendered by DuckDB"
    }
  ],
  "title": "Hello world",
  "total_rows": 1
}
```

**Notes**

- status_code: 200
- content_type: application/json

### 4. Apply per-cell override to annotate the note

**Command**

```python
client.post("/routes/hello_world/overrides", json=override_payload)
```

**Request JSON**

```json
{
  "column": "note",
  "key": {
    "greeting": "Hello, River!"
  },
  "reason": "Document remote context before sharing",
  "value": "Ops fix: River is remote-first"
}
```

**Response JSON**

```json
{
  "override": {
    "author_hash": null,
    "author_user_id": "ops.lead@example.com",
    "column": "note",
    "created_ts": 1762232493.540128,
    "reason": "Document remote context before sharing",
    "route_id": "hello_world",
    "row_key": "{\"greeting\": \"Hello, River!\"}",
    "value": "Ops fix: River is remote-first"
  }
}
```

**Notes**

- status_code: 200
- content_type: application/json

### 5. Route response after override

**Command**

```python
client.get("/hello", params={"name": "River", "format": "json"})
```

**Query Parameters**

```json
{
  "format": "json",
  "name": "River"
}
```

**Response JSON**

```json
{
  "charts": [
    {
      "html": "<svg viewBox='0 0 400 160' role='img' aria-label='Line chart'><polyline fill='none' stroke='#3b82f6' stroke-width='2' points='12.0,80.0'/></svg>",
      "id": "greeting_length"
    }
  ],
  "columns": [
    "greeting",
    "note",
    "greeting_length",
    "created_at"
  ],
  "description": "Return a greeting using DuckDB",
  "elapsed_ms": 3.96,
  "limit": null,
  "offset": 0,
  "route_id": "hello_world",
  "row_count": 1,
  "rows": [
    {
      "created_at": "2025-11-04T05:01:33.481496+00:00",
      "greeting": "Hello, River!",
      "greeting_length": 13,
      "note": "Ops fix: River is remote-first"
    }
  ],
  "title": "Hello world",
  "total_rows": 1
}
```

**Notes**

- status_code: 200
- content_type: application/json

### 6. Log the decision via append

**Command**

```python
client.post("/routes/hello_world/append", json=append_payload)
```

**Request JSON**

```json
{
  "created_at": "2025-11-04T05:01:33.548594+00:00",
  "greeting": "Hello, River!",
  "note": "Ops fix: River is remote-first"
}
```

**Response JSON**

```json
{
  "appended": true,
  "path": "/workspace/webbed_duck/demos/fix-and-forward/_workspace/storage/runtime/appends/hello_appends.csv"
}
```

**Notes**

- status_code: 200
- content_type: application/json

### 7. Inspect append log artifact

**Command**

```python
append_path.read_text(encoding="utf-8")
```

**Response**

```text
greeting,note,created_at
"Hello, River!",Ops fix: River is remote-first,2025-11-04T05:01:33.548594+00:00
```

**Notes**

- path: /workspace/webbed_duck/demos/fix-and-forward/_workspace/storage/runtime/appends/hello_appends.csv

### 8. Resolve local reference with redaction for automation

**Command**

```python
client.post("/local/resolve", json=local_payload)
```

**Request JSON**

```json
{
  "format": "json",
  "params": {
    "name": "River"
  },
  "record_analytics": false,
  "redact_columns": [
    "note"
  ],
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
    "greeting"
  ],
  "description": "Return a greeting using DuckDB",
  "elapsed_ms": 3.569,
  "limit": null,
  "offset": 0,
  "route_id": "hello_world",
  "row_count": 1,
  "rows": [
    {
      "greeting": "Hello, River!"
    }
  ],
  "title": "Hello world",
  "total_rows": 1
}
```

**Notes**

- status_code: 200
- content_type: application/json

### 9. Issue a share link without sending email

**Command**

```python
client.post("/routes/hello_world/share", json=share_payload)
```

**Request JSON**

```json
{
  "emails": [
    "ally@example.com"
  ],
  "format": "html_t",
  "max_rows": 1,
  "params": {
    "name": "River"
  }
}
```

**Response JSON**

```json
{
  "share": {
    "attachments": [],
    "expires_at": "2025-11-04T06:31:33.562635+00:00",
    "format": "html_t",
    "inline_snapshot": true,
    "redacted_columns": [],
    "rows_shared": 1,
    "token": "gsAD-1dP5l0caSxcENLUXS8MuJdf4ALZ3Xc383bWGOk",
    "total_rows": 1,
    "url": "http://testserver/shares/gsAD-1dP5l0caSxcENLUXS8MuJdf4ALZ3Xc383bWGOk",
    "watermark": true,
    "zip_encrypted": false,
    "zipped": false
  }
}
```

**Notes**

- status_code: 200
- content_type: application/json

### 10. Fetch the shared snapshot as JSON

**Command**

```python
client.get(f"/shares/{share_token}", params={"format": "json", "limit": 1, "column": "greeting"})
```

**Query Parameters**

```json
{
  "column": "greeting",
  "format": "json",
  "limit": 1
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
    "greeting"
  ],
  "description": "Return a greeting using DuckDB",
  "elapsed_ms": 3.072,
  "limit": 1,
  "offset": 0,
  "route_id": "hello_world",
  "row_count": 1,
  "rows": [
    {
      "greeting": "Hello, River!"
    }
  ],
  "title": "Hello world",
  "total_rows": 1
}
```

**Notes**

- status_code: 200
- content_type: application/json

### 11. Review route analytics after the workflow

**Command**

```python
client.get("/routes")
```

**Response JSON**

```json
{
  "route_summary": {
    "append": null,
    "id": "hello_world",
    "metrics": {
      "avg_latency_ms": 49.438,
      "hits": 2,
      "interactions": 1,
      "rows": 2
    },
    "overrides": null,
    "title": "Hello world"
  }
}
```

**Notes**

- status_code: 200
- content_type: application/json
