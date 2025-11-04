<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->
# Surprise Workflow Demo

Generated on 2025-11-04T05:00:03.272877+00:00 UTC.

This walk-through stitches together pseudo-auth sessions, append storage, cell overrides, local route chaining, and share links to showcase how WebDuck workflows compound when orchestrated intentionally.

## Feature toggles during capture

- `auth.mode = "pseudo"`
- `feature_flags.overrides_enabled = true`
- `feature_flags.annotations_enabled = true`
- `feature_flags.comments_enabled = true`
- `feature_flags.tasks_enabled = true`

## HTTP transcript

### 1. Start pseudo session

**Request**

```http
POST /auth/pseudo/session HTTP/1.1
host: testserver
user-agent: demo-generator
accept: application/json
```

**Request JSON**

```json
{
  "email": "analyst@example.com",
  "remember_me": false
}
```

**Response JSON**

```json
{
  "body": {
    "user": {
      "email_hash": "506729b248c4d43123200937f9b162d3cd3c5a0617fbc02ab691e5dda8f56428",
      "expires_at": "2025-11-04T05:45:03.362262+00:00",
      "id": "analyst@example.com"
    }
  },
  "status_code": 200
}
```

**Why it matters**

- Creates a pseudo-auth session so overrides and shares capture the analyst's identity.

### 2. Inspect route schema and form metadata

**Request**

```http
GET /routes/hello_world/schema HTTP/1.1
host: testserver
user-agent: demo-generator
accept: application/json
```

**Response JSON**

```json
{
  "body": {
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
  },
  "status_code": 200
}
```

**Why it matters**

- Shows the auto-generated parameter form and the override/append capabilities baked into the route metadata.

### 3. Render the greeting before overrides

**Request**

```http
GET /hello?format=json&name=Surprise+Workflow HTTP/1.1
host: testserver
user-agent: demo-generator
accept: application/json
```

**Response JSON**

```json
{
  "body": {
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
    "elapsed_ms": 58.024,
    "limit": null,
    "offset": 0,
    "route_id": "hello_world",
    "row_count": 1,
    "rows": [
      {
        "created_at": "2025-11-04T05:00:03.438343+00:00",
        "greeting": "Hello, Surprise Workflow!",
        "greeting_length": 25,
        "note": "Personalized greeting rendered by DuckDB"
      }
    ],
    "title": "Hello world",
    "total_rows": 1
  },
  "status_code": 200
}
```

**Why it matters**

- Baseline JSON response that will be augmented by later steps.

### 4. Persist the greeting via CSV append

**Request**

```http
POST /routes/hello_world/append HTTP/1.1
host: testserver
user-agent: demo-generator
accept: application/json
```

**Request JSON**

```json
{
  "created_at": "2025-11-04T05:00:03.488472+00:00",
  "greeting": "Hello, Surprise Workflow!",
  "note": "Appended from the surprise workflow demo"
}
```

**Response JSON**

```json
{
  "body": {
    "appended": true,
    "path": "/workspace/webbed_duck/demos/surprise-workflow/_workspace/storage/runtime/appends/hello_appends.csv"
  },
  "status_code": 200
}
```

**Why it matters**

- Captures the live greeting in append storage so downstream tools can reuse it without re-running the query.

### 5. Apply a cell-level override

**Request**

```http
POST /routes/hello_world/overrides HTTP/1.1
host: testserver
user-agent: demo-generator
accept: application/json
```

**Request JSON**

```json
{
  "author": "demo-bot",
  "column": "note",
  "reason": "Annotate the persisted greeting for teammates",
  "row_key": "{\"greeting\": \"Hello, Surprise Workflow!\"}",
  "value": "Blends append storage with a live override to narrate the workflow."
}
```

**Response JSON**

```json
{
  "body": {
    "override": {
      "author_hash": "3d92d150fdd73fb05057fd5c8e1d8b0cbce49f7268e6078c8cf0eed3ef244a27",
      "author_user_id": "analyst@example.com",
      "column": "note",
      "created_ts": 1762232403.497456,
      "reason": "Annotate the persisted greeting for teammates",
      "route_id": "hello_world",
      "row_key": "{\"greeting\": \"Hello, Surprise Workflow!\"}",
      "value": "Blends append storage with a live override to narrate the workflow."
    }
  },
  "status_code": 200
}
```

**Why it matters**

- Overrides the note column for this specific greeting so collaborators see curated guidance next to the data.

### 6. Re-run the greeting with overrides applied

**Request**

```http
GET /hello?format=json&name=Surprise+Workflow HTTP/1.1
host: testserver
user-agent: demo-generator
accept: application/json
```

**Response JSON**

```json
{
  "body": {
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
    "elapsed_ms": 4.031,
    "limit": null,
    "offset": 0,
    "route_id": "hello_world",
    "row_count": 1,
    "rows": [
      {
        "created_at": "2025-11-04T05:00:03.438343+00:00",
        "greeting": "Hello, Surprise Workflow!",
        "greeting_length": 25,
        "note": "Blends append storage with a live override to narrate the workflow."
      }
    ],
    "title": "Hello world",
    "total_rows": 1
  },
  "status_code": 200
}
```

**Why it matters**

- Shows the override being layered on top of the cached query result — no SQL edits required.

### 7. Resolve the same slice through /local/resolve

**Request**

```http
POST /local/resolve HTTP/1.1
host: testserver
user-agent: demo-generator
accept: application/json
```

**Request JSON**

```json
{
  "columns": [
    "greeting",
    "note"
  ],
  "format": "json",
  "params": {
    "name": "Surprise Workflow"
  },
  "record_analytics": false,
  "reference": "local:hello_world"
}
```

**Response JSON**

```json
{
  "body": {
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
    "elapsed_ms": 2.594,
    "limit": null,
    "offset": 0,
    "route_id": "hello_world",
    "row_count": 1,
    "rows": [
      {
        "greeting": "Hello, Surprise Workflow!",
        "note": "Blends append storage with a live override to narrate the workflow."
      }
    ],
    "title": "Hello world",
    "total_rows": 1
  },
  "status_code": 200
}
```

**Why it matters**

- Demonstrates chaining the curated slice inside other routes or automations without touching HTTP clients.

### 8. Create a share link with the curated slice

**Request**

```http
POST /routes/hello_world/share HTTP/1.1
host: testserver
user-agent: demo-generator
accept: application/json
```

**Request JSON**

```json
{
  "emails": [
    "teammate@example.com"
  ],
  "format": "json",
  "params": {
    "name": "Surprise Workflow"
  }
}
```

**Response JSON**

```json
{
  "body": {
    "share": {
      "attachments": [],
      "expires_at": "2025-11-04T06:30:03.515564+00:00",
      "format": "json",
      "inline_snapshot": true,
      "redacted_columns": [],
      "rows_shared": 1,
      "token": "4W9ZdFvlal-5ZgxxhSb42SRZMvHUHmsTKM93OQOdxXQ",
      "total_rows": 1,
      "url": "http://testserver/shares/4W9ZdFvlal-5ZgxxhSb42SRZMvHUHmsTKM93OQOdxXQ",
      "watermark": true,
      "zip_encrypted": false,
      "zipped": false
    }
  },
  "status_code": 200
}
```

**Why it matters**

- Bundles the override-enhanced view so teammates receive the annotated greeting and Arrow/JSON attachments.

### 9. Resolve the share token

**Request**

```http
GET /shares/4W9ZdFvlal-5ZgxxhSb42SRZMvHUHmsTKM93OQOdxXQ?format=json HTTP/1.1
host: testserver
user-agent: demo-generator
accept: application/json
```

**Response JSON**

```json
{
  "body": {
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
    "elapsed_ms": 2.225,
    "limit": null,
    "offset": 0,
    "route_id": "hello_world",
    "row_count": 1,
    "rows": [
      {
        "created_at": "2025-11-04T05:00:03.438343+00:00",
        "greeting": "Hello, Surprise Workflow!",
        "greeting_length": 25,
        "note": "Blends append storage with a live override to narrate the workflow."
      }
    ],
    "title": "Hello world",
    "total_rows": 1
  },
  "status_code": 200
}
```

**Why it matters**

- Verifies that the public share faithfully reproduces the overridden note without re-authenticating.

## Append storage snapshot

```csv
greeting,note,created_at
"Hello, Surprise Workflow!",Appended from the surprise workflow demo,2025-11-04T05:00:03.488472+00:00
```

## Override ledger

```json
{
  "overrides": [
    {
      "author_hash": "3d92d150fdd73fb05057fd5c8e1d8b0cbce49f7268e6078c8cf0eed3ef244a27",
      "author_user_id": "analyst@example.com",
      "column": "note",
      "created_ts": 1762232403.497456,
      "reason": "Annotate the persisted greeting for teammates",
      "route_id": "hello_world",
      "row_key": "{\"greeting\": \"Hello, Surprise Workflow!\"}",
      "value": "Blends append storage with a live override to narrate the workflow."
    }
  ],
  "route_id": "hello_world"
}
```
