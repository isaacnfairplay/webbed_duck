<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->
# Annotated Share Workflow Demo

Generated on 2025-11-04 05:00:44Z UTC.

This walkthrough pairs pseudo-auth overrides with share redaction so teams can annotate a slice for themselves while sending a sanitized export.

## Feature toggles applied during the run

- **server.storage_root**: `PosixPath('storage')` → `PosixPath('/workspace/webbed_duck/demos/annotated-share/runtime/storage')`
- **server.build_dir**: `PosixPath('routes_build')` → `PosixPath('/workspace/webbed_duck/demos/annotated-share/runtime/build')`
- **server.source_dir**: `PosixPath('routes_src')` → `None`
- **server.auto_compile**: `True` → `False`
- **server.watch**: `False` → `False`
- **server.host**: `'127.0.0.1'` → `'127.0.0.1'`
- **server.port**: `8000` → `44433`
- **auth.mode**: `'none'` → `'pseudo'`
- **feature_flags.overrides_enabled**: `False` → `True`
- **email.adapter**: `None` → `None`
- **email.bind_share_to_user_agent**: `False` → `True`
- **email.bind_share_to_ip_prefix**: `False` → `True`

## Local runner snapshot before overrides

```json
[
  {
    "created_at": "2025-11-04T05:00:31.797693+00:00",
    "greeting": "Hello, Narrative Surprise!",
    "greeting_length": 26,
    "note": "Personalized greeting rendered by DuckDB"
  }
]
```

Row key used for overrides:

```json
"{\"greeting\": \"Hello, Narrative Surprise!\"}"
```

## HTTP interactions

### 1. Create pseudo session

**Request**

```http
POST /auth/pseudo/session HTTP/1.1
Host: 127.0.0.1:44433
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
User-Agent: annotated-share-demo/1.0
Content-Length: 52
Content-Type: application/json

{
  "email": "surprise@example.com",
  "remember_me": false
}
```

**Response**

```http
HTTP/1.1 200 OK
date: Tue, 04 Nov 2025 05:00:43 GMT
server: uvicorn
content-length: 166
content-type: application/json
set-cookie: wd_session=7yUcpEMXSC7naSIYjEt00yGFrBjVklQB-aCKEJiWXOs; HttpOnly; Max-Age=2699; Path=/; SameSite=lax

{
  "user": {
    "email_hash": "b34e3bcc2e30232400c5139fc8bcf815130e4ee3f9e57cc2f8ef0bbd84b25a1b",
    "expires_at": "2025-11-04T05:45:43.956390+00:00",
    "id": "surprise@example.com"
  }
}
```

### 2. Apply override to note column

**Request**

```http
POST /routes/hello_world/overrides HTTP/1.1
Host: 127.0.0.1:44433
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
User-Agent: annotated-share-demo/1.0
Cookie: wd_session=7yUcpEMXSC7naSIYjEt00yGFrBjVklQB-aCKEJiWXOs
Content-Length: 201
Content-Type: application/json

{
  "author": "annotated-share-demo@company.local",
  "column": "note",
  "key": {
    "greeting": "Hello, Narrative Surprise!"
  },
  "reason": "Annotating before sharing",
  "value": "Override note authored by generate_demo.py"
}
```

**Response**

```http
HTTP/1.1 200 OK
date: Tue, 04 Nov 2025 05:00:43 GMT
server: uvicorn
content-length: 356
content-type: application/json

{
  "override": {
    "author_hash": "46de3f39029c5119aec280f98287c5ce199132513b626d1ba45ed3c475279cd7",
    "author_user_id": "surprise@example.com",
    "column": "note",
    "created_ts": 1762232443.966938,
    "reason": "Annotating before sharing",
    "route_id": "hello_world",
    "row_key": "{\"greeting\": \"Hello, Narrative Surprise!\"}",
    "value": "Override note authored by generate_demo.py"
  }
}
```

### 3. Fetch JSON render with override

**Request**

```http
GET /hello?format=json&name=Narrative+Surprise HTTP/1.1
Host: 127.0.0.1:44433
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
User-Agent: annotated-share-demo/1.0
Cookie: wd_session=7yUcpEMXSC7naSIYjEt00yGFrBjVklQB-aCKEJiWXOs
```

**Response**

```http
HTTP/1.1 200 OK
date: Tue, 04 Nov 2025 05:00:43 GMT
server: uvicorn
content-length: 590
content-type: application/json

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
  "elapsed_ms": 5.111,
  "limit": null,
  "offset": 0,
  "route_id": "hello_world",
  "row_count": 1,
  "rows": [
    {
      "created_at": "2025-11-04T05:00:31.797693+00:00",
      "greeting": "Hello, Narrative Surprise!",
      "greeting_length": 26,
      "note": "Override note authored by generate_demo.py"
    }
  ],
  "title": "Hello world",
  "total_rows": 1
}
```

### 4. Create redacted share

**Request**

```http
POST /routes/hello_world/share HTTP/1.1
Host: 127.0.0.1:44433
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
User-Agent: annotated-share-demo/1.0
Cookie: wd_session=7yUcpEMXSC7naSIYjEt00yGFrBjVklQB-aCKEJiWXOs
Content-Length: 141
Content-Type: application/json

{
  "emails": [
    "teammate@example.com"
  ],
  "format": "json",
  "params": {
    "name": "Narrative Surprise"
  },
  "record_analytics": false,
  "redact_columns": [
    "note"
  ]
}
```

**Response**

```http
HTTP/1.1 200 OK
date: Tue, 04 Nov 2025 05:00:43 GMT
server: uvicorn
content-length: 364
content-type: application/json

{
  "share": {
    "attachments": [],
    "expires_at": "2025-11-04T06:30:43.979280+00:00",
    "format": "json",
    "inline_snapshot": true,
    "redacted_columns": [
      "note"
    ],
    "rows_shared": 1,
    "token": "xFiHW-RQntZ8e3xmdFjnNbQOQSGLifMoTQamgGC2J2E",
    "total_rows": 1,
    "url": "http://127.0.0.1:44433/shares/xFiHW-RQntZ8e3xmdFjnNbQOQSGLifMoTQamgGC2J2E",
    "watermark": true,
    "zip_encrypted": false,
    "zipped": false
  }
}
```

### 5. Resolve share token

**Request**

```http
GET /shares/xFiHW-RQntZ8e3xmdFjnNbQOQSGLifMoTQamgGC2J2E?format=json HTTP/1.1
Host: 127.0.0.1:44433
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
User-Agent: annotated-share-demo/1.0
Cookie: wd_session=7yUcpEMXSC7naSIYjEt00yGFrBjVklQB-aCKEJiWXOs
```

**Response**

```http
HTTP/1.1 200 OK
date: Tue, 04 Nov 2025 05:00:43 GMT
server: uvicorn
content-length: 531
content-type: application/json

{
  "charts": [
    {
      "html": "<svg viewBox='0 0 400 160' role='img' aria-label='Line chart'><polyline fill='none' stroke='#3b82f6' stroke-width='2' points='12.0,80.0'/></svg>",
      "id": "greeting_length"
    }
  ],
  "columns": [
    "greeting",
    "greeting_length",
    "created_at"
  ],
  "description": "Return a greeting using DuckDB",
  "elapsed_ms": 1.839,
  "limit": null,
  "offset": 0,
  "route_id": "hello_world",
  "row_count": 1,
  "rows": [
    {
      "created_at": "2025-11-04T05:00:31.797693+00:00",
      "greeting": "Hello, Narrative Surprise!",
      "greeting_length": 26
    }
  ],
  "title": "Hello world",
  "total_rows": 1
}
```

### 6. List overrides for route

**Request**

```http
GET /routes/hello_world/overrides HTTP/1.1
Host: 127.0.0.1:44433
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
User-Agent: annotated-share-demo/1.0
Cookie: wd_session=7yUcpEMXSC7naSIYjEt00yGFrBjVklQB-aCKEJiWXOs
```

**Response**

```http
HTTP/1.1 200 OK
date: Tue, 04 Nov 2025 05:00:43 GMT
server: uvicorn
content-length: 384
content-type: application/json

{
  "overrides": [
    {
      "author_hash": "46de3f39029c5119aec280f98287c5ce199132513b626d1ba45ed3c475279cd7",
      "author_user_id": "surprise@example.com",
      "column": "note",
      "created_ts": 1762232443.966938,
      "reason": "Annotating before sharing",
      "route_id": "hello_world",
      "row_key": "{\"greeting\": \"Hello, Narrative Surprise!\"}",
      "value": "Override note authored by generate_demo.py"
    }
  ],
  "route_id": "hello_world"
}
```

### 7. Delete pseudo session

**Request**

```http
DELETE /auth/pseudo/session HTTP/1.1
Host: 127.0.0.1:44433
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
User-Agent: annotated-share-demo/1.0
Cookie: wd_session=7yUcpEMXSC7naSIYjEt00yGFrBjVklQB-aCKEJiWXOs
```

**Response**

```http
HTTP/1.1 200 OK
date: Tue, 04 Nov 2025 05:00:43 GMT
server: uvicorn
content-length: 16
content-type: application/json
set-cookie: wd_session=""; expires=Tue, 04 Nov 2025 05:00:43 GMT; Max-Age=0; Path=/; SameSite=lax

{
  "deleted": true
}
```

## Local runner snapshot after override

```json
[
  {
    "created_at": "2025-11-04T05:00:31.797693+00:00",
    "greeting": "Hello, Narrative Surprise!",
    "greeting_length": 26,
    "note": "Override note authored by generate_demo.py"
  }
]
```

## Share metadata

```json
{
  "attachments": [],
  "expires_at": "2025-11-04T06:30:43.979280+00:00",
  "format": "json",
  "inline_snapshot": true,
  "redacted_columns": [
    "note"
  ],
  "rows_shared": 1,
  "token": "xFiHW-RQntZ8e3xmdFjnNbQOQSGLifMoTQamgGC2J2E",
  "total_rows": 1,
  "url": "http://127.0.0.1:44433/shares/xFiHW-RQntZ8e3xmdFjnNbQOQSGLifMoTQamgGC2J2E",
  "watermark": true,
  "zip_encrypted": false,
  "zipped": false
}
```

## Share resolution payload (redacted view)

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
    "greeting_length",
    "created_at"
  ],
  "description": "Return a greeting using DuckDB",
  "elapsed_ms": 1.839,
  "limit": null,
  "offset": 0,
  "route_id": "hello_world",
  "row_count": 1,
  "rows": [
    {
      "created_at": "2025-11-04T05:00:31.797693+00:00",
      "greeting": "Hello, Narrative Surprise!",
      "greeting_length": 26
    }
  ],
  "title": "Hello world",
  "total_rows": 1
}
```

## Meta store snapshots

### After HTTP flows

```json
{
  "shares": [
    {
      "expires_at": "2025-11-04T06:30:43.979280+00:00",
      "format": "json",
      "route_id": "hello_world",
      "token_hash": "8dc75a451542d26cdb5fbaa172bc06cb72f1db841ae2f5e3341f210fd334142f"
    }
  ]
}
```

## Cleanup summary

- Removed share row from meta store
- Cleared overrides.json so reruns start fresh
