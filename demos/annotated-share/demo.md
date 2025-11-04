<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->
# Annotated Share Workflow Demo

This walkthrough combines schema introspection, overlays, local execution, and multi-format sharing so analysts can see how the pieces fit together.

Generated on 2025-11-04T05:02:01.097905+00:00 UTC.

## Temporary configuration tweaks

Applied during generation and reverted afterwards:

- **auth.mode**: "none" → "pseudo"
- **email.adapter**: null → "annotated_share_email_sink:send_email"
- **feature_flags.overrides_enabled**: false → true
- **share.zip_attachments**: true → false

## Walkthrough

### 1. Create pseudo session

**Command**

```python
client.post("/auth/pseudo/session", json=login_payload)
```

**Request JSON**

```json
{
  "email": "workflow.demo@example.com"
}
```

**Response JSON**

```json
{
  "user": {
    "email_hash": "c4f391219ae886a965e8bd41db6a36b431c633f8fce1d1791c596d7c25388aa5",
    "expires_at": "2025-11-04T05:47:00.927361+00:00",
    "id": "workflow.demo@example.com"
  }
}
```

### 2. Inspect route schema and auto-form metadata

**Command**

```python
client.get("/routes/hello_world/schema")
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

- Highlights auto-generated filters and override metadata.

### 3. Submit override for the greeting row

**Command**

```python
client.post("/routes/hello_world/overrides", json=override_payload)
```

**Request JSON**

```json
{
  "author": "workflow.demo@example.com",
  "column": "note",
  "key": {
    "greeting": "Hello, Workflow Demo!"
  },
  "reason": "Pre-share annotation",
  "row_key": "{\"greeting\": \"Hello, Workflow Demo!\"}",
  "value": "Workflow override captured by generate_demo.py"
}
```

**Response JSON**

```json
{
  "override": {
    "author_hash": "c4f391219ae886a965e8bd41db6a36b431c633f8fce1d1791c596d7c25388aa5",
    "author_user_id": "workflow.demo@example.com",
    "column": "note",
    "created_ts": 1762232521.0264,
    "reason": "Pre-share annotation",
    "route_id": "hello_world",
    "row_key": "{\"greeting\": \"Hello, Workflow Demo!\"}",
    "value": "Workflow override captured by generate_demo.py"
  }
}
```

**Notes**

- Row key computed via `compute_row_key_from_values`.
- Recorded author hash proves provenance.

### 4. LocalRouteRunner view after override

**Command**

```python
runner.run("hello_world", params={"name": "Workflow Demo"}, format="records")
```

**Response JSON**

```json
{
  "rows": [
    {
      "created_at": "2025-11-04T05:02:01.047669+00:00",
      "greeting": "Hello, Workflow Demo!",
      "greeting_length": 21,
      "note": "Workflow override captured by generate_demo.py"
    }
  ]
}
```

**Notes**

- Local execution picks up the override without HTTP.
- Note column reflects the annotated value.

### 5. Create share with inline snapshot and attachments

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
  "emails": [
    "stakeholder@example.com"
  ],
  "format": "html_t",
  "inline_snapshot": true,
  "params": {
    "name": "Workflow Demo"
  },
  "watermark": true
}
```

**Response JSON**

```json
{
  "share": {
    "attachments": [
      "hello_world.csv",
      "hello_world.html"
    ],
    "expires_at": "2025-11-04T06:32:01.080608+00:00",
    "format": "html_t",
    "inline_snapshot": true,
    "redacted_columns": [],
    "rows_shared": 1,
    "token": "c9Mg5MRjPvGnNid7mABn-Rql71r5H-LGAc8J-qcf_3M",
    "total_rows": 1,
    "url": "http://testserver/shares/c9Mg5MRjPvGnNid7mABn-Rql71r5H-LGAc8J-qcf_3M",
    "watermark": true,
    "zip_encrypted": false,
    "zipped": false
  }
}
```

**Notes**

- Share token: c9Mg5MRjPvGnNid7mABn-Rql71r5H-LGAc8J-qcf_3M
- Attachments returned: ['hello_world.csv', 'hello_world.html']
- Rows shared: 1

### 6. Captured outbound share email

**Command**

```python
sent_emails[-1]
```

**Response JSON**

```json
{
  "attachments": [
    "hello_world.csv",
    "hello_world.html"
  ],
  "html_excerpt": "<!doctype html><meta charset='utf-8'><h3>Hello world</h3><p>workflow.demo shared a view with you.</p><p><a href='http://testserver/shares/c9Mg5MRjPvGnNid7mABn-Rql71r5H-LGAc8J-qcf_3M'>Open the share</a\u2026",
  "subject": "Hello world shared with you",
  "to": [
    "stakeholder@example.com"
  ]
}
```

**Notes**

- Stub adapter captures the audience and attachment filenames.

### 7. Fetch delivered share payload

**Command**

```python
client.get(f"/shares/{share_token}?format=json")
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
  "elapsed_ms": 2.278,
  "limit": null,
  "offset": 0,
  "route_id": "hello_world",
  "row_count": 1,
  "rows": [
    {
      "created_at": "2025-11-04T05:02:01.047669+00:00",
      "greeting": "Hello, Workflow Demo!",
      "greeting_length": 21,
      "note": "Workflow override captured by generate_demo.py"
    }
  ],
  "title": "Hello world",
  "total_rows": 1
}
```

**Notes**

- Override survives into the shared rows.
