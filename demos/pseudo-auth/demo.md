# Pseudo Authentication & Share Demo

_Generated automatically at 2025-11-04 02:47:50Z UTC by running `python demos/pseudo-auth/generate_demo.py`._

> Pseudo authentication is intended for trusted intranets. Deploy behind a hardened proxy and external identity provider before exposing these endpoints to the public internet.

## Environment setup

* Base URL: `http://127.0.0.1:34333`
* Runtime directory: `demos/pseudo-auth/runtime`
* Storage root: `demos/pseudo-auth/runtime/storage`
* Routes compiled from: `routes_src` → `demos/pseudo-auth/runtime/build`

## HTTP interactions

### 1. Create pseudo session

**Request**

```http
POST /auth/pseudo/session HTTP/1.1
Host: 127.0.0.1:34333
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
User-Agent: pseudo-auth-demo/1.0
Content-Length: 50
Content-Type: application/json

{
  "email": "analyst@example.com",
  "remember_me": true
}
```

**Response**

```http
HTTP/1.1 200 OK
date: Tue, 04 Nov 2025 02:47:50 GMT
server: uvicorn
content-length: 165
content-type: application/json
set-cookie: wd_session=i7G7GiGSAiL7_cp4frOhfWcXJppbUX4s0mGf-5itrII; HttpOnly; Max-Age=604799; Path=/; SameSite=lax

{
  "user": {
    "email_hash": "506729b248c4d43123200937f9b162d3cd3c5a0617fbc02ab691e5dda8f56428",
    "expires_at": "2025-11-11T02:47:50.152425+00:00",
    "id": "analyst@example.com"
  }
}
```

### 2. Inspect current session

**Request**

```http
GET /auth/pseudo/session HTTP/1.1
Host: 127.0.0.1:34333
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
User-Agent: pseudo-auth-demo/1.0
Cookie: wd_session=i7G7GiGSAiL7_cp4frOhfWcXJppbUX4s0mGf-5itrII
```

**Response**

```http
HTTP/1.1 200 OK
date: Tue, 04 Nov 2025 02:47:50 GMT
server: uvicorn
content-length: 142
content-type: application/json

{
  "user": {
    "display_name": "analyst",
    "email_hash": "506729b248c4d43123200937f9b162d3cd3c5a0617fbc02ab691e5dda8f56428",
    "id": "analyst@example.com"
  }
}
```

### 3. Create share for hello_world

**Request**

```http
POST /routes/hello_world/share HTTP/1.1
Host: 127.0.0.1:34333
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
User-Agent: pseudo-auth-demo/1.0
Cookie: wd_session=i7G7GiGSAiL7_cp4frOhfWcXJppbUX4s0mGf-5itrII
Content-Length: 83
Content-Type: application/json

{
  "emails": [
    "teammate@example.com"
  ],
  "format": "json",
  "params": {
    "name": "Pseudo Demo"
  }
}
```

**Response**

```http
HTTP/1.1 200 OK
date: Tue, 04 Nov 2025 02:47:50 GMT
server: uvicorn
content-length: 358
content-type: application/json

{
  "share": {
    "attachments": [],
    "expires_at": "2025-11-04T04:17:50.162039+00:00",
    "format": "json",
    "inline_snapshot": true,
    "redacted_columns": [],
    "rows_shared": 1,
    "token": "f79ETU98-404vWM1fz2JDfV64EfpGQiyTQpYa-vSKIw",
    "total_rows": 1,
    "url": "http://127.0.0.1:34333/shares/f79ETU98-404vWM1fz2JDfV64EfpGQiyTQpYa-vSKIw",
    "watermark": true,
    "zip_encrypted": false,
    "zipped": false
  }
}
```

### 4. Resolve share token

**Request**

```http
GET /shares/f79ETU98-404vWM1fz2JDfV64EfpGQiyTQpYa-vSKIw?format=json HTTP/1.1
Host: 127.0.0.1:34333
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
User-Agent: pseudo-auth-demo/1.0
Cookie: wd_session=i7G7GiGSAiL7_cp4frOhfWcXJppbUX4s0mGf-5itrII
```

**Response**

```http
HTTP/1.1 200 OK
date: Tue, 04 Nov 2025 02:47:50 GMT
server: uvicorn
content-length: 581
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
  "elapsed_ms": 1.868,
  "limit": null,
  "offset": 0,
  "route_id": "hello_world",
  "row_count": 1,
  "rows": [
    {
      "created_at": "2025-11-04T02:47:28.404751+00:00",
      "greeting": "Hello, Pseudo Demo!",
      "greeting_length": 19,
      "note": "Personalized greeting rendered by DuckDB"
    }
  ],
  "title": "Hello world",
  "total_rows": 1
}
```

### 5. Resolve route via /local/resolve

**Request**

```http
POST /local/resolve HTTP/1.1
Host: 127.0.0.1:34333
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
User-Agent: pseudo-auth-demo/1.0
Cookie: wd_session=i7G7GiGSAiL7_cp4frOhfWcXJppbUX4s0mGf-5itrII
Content-Length: 153
Content-Type: application/json

{
  "columns": [
    "greeting"
  ],
  "format": "json",
  "params": {
    "name": "Pseudo Demo"
  },
  "record_analytics": false,
  "reference": "local:hello_world?limit=1&column=greeting"
}
```

**Response**

```http
HTTP/1.1 200 OK
date: Tue, 04 Nov 2025 02:47:50 GMT
server: uvicorn
content-length: 369
content-type: application/json

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
  "elapsed_ms": 1.359,
  "limit": 1,
  "offset": 0,
  "route_id": "hello_world",
  "row_count": 1,
  "rows": [
    {
      "greeting": "Hello, Pseudo Demo!"
    }
  ],
  "title": "Hello world",
  "total_rows": 1
}
```

### 6. Delete pseudo session

**Request**

```http
DELETE /auth/pseudo/session HTTP/1.1
Host: 127.0.0.1:34333
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
User-Agent: pseudo-auth-demo/1.0
Cookie: wd_session=i7G7GiGSAiL7_cp4frOhfWcXJppbUX4s0mGf-5itrII
```

**Response**

```http
HTTP/1.1 200 OK
date: Tue, 04 Nov 2025 02:47:50 GMT
server: uvicorn
content-length: 16
content-type: application/json
set-cookie: wd_session=""; expires=Tue, 04 Nov 2025 02:47:50 GMT; Max-Age=0; Path=/; SameSite=lax

{
  "deleted": true
}
```

## Share metadata

```json
{
  "attachments": [],
  "expires_at": "2025-11-04T04:17:50.162039+00:00",
  "format": "json",
  "inline_snapshot": true,
  "redacted_columns": [],
  "rows_shared": 1,
  "token": "f79ETU98-404vWM1fz2JDfV64EfpGQiyTQpYa-vSKIw",
  "total_rows": 1,
  "url": "http://127.0.0.1:34333/shares/f79ETU98-404vWM1fz2JDfV64EfpGQiyTQpYa-vSKIw",
  "watermark": true,
  "zip_encrypted": false,
  "zipped": false
}
```

## Share resolution payload

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
  "elapsed_ms": 1.868,
  "limit": null,
  "offset": 0,
  "route_id": "hello_world",
  "row_count": 1,
  "rows": [
    {
      "created_at": "2025-11-04T02:47:28.404751+00:00",
      "greeting": "Hello, Pseudo Demo!",
      "greeting_length": 19,
      "note": "Personalized greeting rendered by DuckDB"
    }
  ],
  "title": "Hello world",
  "total_rows": 1
}
```

## Local `/local/resolve` response

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
  "elapsed_ms": 1.359,
  "limit": 1,
  "offset": 0,
  "route_id": "hello_world",
  "row_count": 1,
  "rows": [
    {
      "greeting": "Hello, Pseudo Demo!"
    }
  ],
  "title": "Hello world",
  "total_rows": 1
}
```

## Meta store snapshots

### After share creation

**Sessions table**

```json
[
  {
    "email": "analyst@example.com",
    "expires_at": "2025-11-11T02:47:50.152425+00:00",
    "token_hash": "bce60cab24362470edf5cc49d689dd99e679d27a7028c5595f0549747f64e9fc"
  }
]
```

**Shares table**

```json
[
  {
    "expires_at": "2025-11-04T04:17:50.162039+00:00",
    "route_id": "hello_world",
    "token_hash": "473853a301fb28367a8f1514f7795ffbe220a629811c6c3aa952ca6002926f16"
  }
]
```

### After DELETE /auth/pseudo/session

**Sessions table**

(empty)

**Shares table**

```json
[
  {
    "expires_at": "2025-11-04T04:17:50.162039+00:00",
    "route_id": "hello_world",
    "token_hash": "473853a301fb28367a8f1514f7795ffbe220a629811c6c3aa952ca6002926f16"
  }
]
```

### After manual cleanup

**Sessions table**

(empty)

**Shares table**

(empty)

## Cleanup summary

Removed share and session rows from the SQLite meta store
