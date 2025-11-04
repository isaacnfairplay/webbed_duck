<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->
# Insight Synergy Demo

Generated on 2025-11-04T05:00:20.087292+00:00 UTC.

## Feature & Auth Toggles

These toggles were applied during the run and restored afterwards:

- **auth.mode**: "none" → "pseudo"
- **feature_flags.overrides_enabled**: false → true

## Command Transcript

### 1. Compile hello route

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

### 2. Local preview before overrides

**Command**

```python
runner.run(route_id="hello_world", params={"name": "Synergy"}, format="records")
```

**Response JSON**

```json
{
  "rows": [
    {
      "created_at": "2025-11-04T05:00:19.862785+00:00",
      "greeting": "Hello, Synergy!",
      "greeting_length": 15,
      "note": "Personalized greeting rendered by DuckDB"
    }
  ]
}
```

### 3. Create pseudo session

**Command**

```python
client.post("/auth/pseudo/session", json=login_payload)
```

**Request JSON**

```json
{
  "display_name": "Insight Builder",
  "email": "analyst@example.com"
}
```

**Response JSON**

```json
{
  "user": {
    "email_hash": "506729b248c4d43123200937f9b162d3cd3c5a0617fbc02ab691e5dda8f56428",
    "expires_at": "2025-11-04T05:45:19.983614+00:00",
    "id": "analyst@example.com"
  }
}
```

**Notes**

- status_code: 200

### 4. Inspect auto-generated form & schema

**Command**

```python
client.get("/routes/hello_world/schema", params={"name": "Synergy"})
```

**Response JSON**

```json
{
  "append": {
    "columns": [
      "greeting",
      "note",
      "created_at"
    ],
    "destination": "hello_appends.csv"
  },
  "form": [
    {
      "default": "world",
      "description": "Name to greet",
      "name": "name",
      "required": false,
      "type": "str"
    }
  ],
  "overrides": {
    "allowed": [
      "note"
    ],
    "key_columns": [
      "greeting"
    ]
  },
  "path": "/hello",
  "route_id": "hello_world",
  "schema": [
    {
      "name": "greeting",
      "type": "string"
    },
    {
      "name": "note",
      "type": "string"
    },
    {
      "name": "greeting_length",
      "type": "int32"
    },
    {
      "name": "created_at",
      "type": "timestamp[us, tz=Etc/UTC]"
    }
  ]
}
```

**Notes**

- status_code: 200

### 5. Apply override through HTTP

**Command**

```python
client.post("/routes/hello_world/overrides", json=override_payload)
```

**Request JSON**

```json
{
  "author": "Insight Builder",
  "column": "note",
  "reason": "Blend local preview with overlays before sharing",
  "row_key": "{\"greeting\": \"Hello, Synergy!\"}",
  "value": "Synergy preview curated via override"
}
```

**Response JSON**

```json
{
  "override": {
    "author_hash": "8cb3d6c2c49511810fd5074c50eb7adf595f9f82efed4ae6718fe16978027133",
    "author_user_id": "analyst@example.com",
    "column": "note",
    "created_ts": 1762232420.031594,
    "reason": "Blend local preview with overlays before sharing",
    "route_id": "hello_world",
    "row_key": "{\"greeting\": \"Hello, Synergy!\"}",
    "value": "Synergy preview curated via override"
  }
}
```

**Notes**

- status_code: 200

### 6. Local preview after override

**Command**

```python
runner.run(route_id="hello_world", params={"name": "Synergy"}, format="records")
```

**Response JSON**

```json
{
  "rows": [
    {
      "created_at": "2025-11-04T05:00:19.862785+00:00",
      "greeting": "Hello, Synergy!",
      "greeting_length": 15,
      "note": "Synergy preview curated via override"
    }
  ]
}
```

### 7. Resolve local reference with analytics

**Command**

```python
client.post("/local/resolve", json=local_payload)
```

**Request JSON**

```json
{
  "format": "json",
  "params": {
    "name": "Synergy"
  },
  "record_analytics": true,
  "reference": "local:hello_world?column=greeting&column=note&column=created_at"
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
    "note",
    "created_at"
  ],
  "description": "Return a greeting using DuckDB",
  "elapsed_ms": 2.396,
  "limit": null,
  "offset": 0,
  "route_id": "hello_world",
  "row_count": 1,
  "rows": [
    {
      "created_at": "2025-11-04T05:00:19.862785+00:00",
      "greeting": "Hello, Synergy!",
      "note": "Synergy preview curated via override"
    }
  ],
  "title": "Hello world",
  "total_rows": 1
}
```

**Notes**

- status_code: 200

### 8. Create curated share with attachments

**Command**

```python
client.post("/routes/hello_world/share", json=share_payload)
```

**Request JSON**

```json
{
  "attachments": [
    "csv",
    "html"
  ],
  "columns": [
    "greeting",
    "note",
    "created_at"
  ],
  "emails": [
    "surprise@stakeholders.local"
  ],
  "format": "json",
  "params": {
    "name": "Synergy"
  },
  "watermark_text": "Synergy share watermark",
  "zip": true,
  "zip_passphrase": "synergy-demo"
}
```

**Response JSON**

```json
{
  "share": {
    "attachments": [
      "hello_world.zip"
    ],
    "expires_at": "2025-11-04T06:30:20.044136+00:00",
    "format": "json",
    "inline_snapshot": true,
    "redacted_columns": [],
    "rows_shared": 1,
    "token": "piBzATLxK52WIhjlYrE_GtXuv5pXfWoIHNax79N27dM",
    "total_rows": 1,
    "url": "http://testserver/shares/piBzATLxK52WIhjlYrE_GtXuv5pXfWoIHNax79N27dM",
    "watermark": true,
    "zip_encrypted": true,
    "zipped": true
  }
}
```

**Notes**

- status_code: 200

### 9. Resolve share token to confirm payload

**Command**

```python
client.get("/shares/piBzATLxK52WIhjlYrE_GtXuv5pXfWoIHNax79N27dM?format=json")
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
  "elapsed_ms": 2.295,
  "limit": null,
  "offset": 0,
  "route_id": "hello_world",
  "row_count": 1,
  "rows": [
    {
      "created_at": "2025-11-04T05:00:19.862785+00:00",
      "greeting": "Hello, Synergy!",
      "greeting_length": 15,
      "note": "Synergy preview curated via override"
    }
  ],
  "title": "Hello world",
  "total_rows": 1
}
```

**Notes**

- status_code: 200

### 10. Inspect route listing with analytics

**Command**

```python
client.get("/routes")
```

**Response JSON**

```json
{
  "folder": "/",
  "folders": [],
  "routes": [
    {
      "description": "Return a greeting using DuckDB",
      "id": "hello_world",
      "metrics": {
        "avg_latency_ms": 2.396,
        "hits": 1,
        "interactions": 1,
        "rows": 1
      },
      "path": "/hello",
      "title": "Hello world"
    }
  ]
}
```

**Notes**

- status_code: 200
