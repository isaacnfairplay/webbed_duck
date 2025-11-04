<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->
# Overlay + Share Fusion Demo

Generated on 2025-11-04T05:04:16.082641+00:00.

This walkthrough starts with an offline LocalRouteRunner preview, then leans on the server's auto-generated parameter form to build a share that already includes a contextual overlay note.

## Local preview before touching HTTP

```json
[
  {
    "created_at": "2025-11-04T05:04:16.306972+00:00",
    "greeting": "Hello, Overlay Share Fusion!",
    "greeting_length": 28,
    "note": "Personalized greeting rendered by DuckDB"
  }
]
```

## HTTP interactions

### 1. Create pseudo session

**Request**

```text
POST /auth/pseudo/session HTTP/1.1
accept: */*
accept-encoding: gzip, deflate
connection: keep-alive
content-length: 50
content-type: application/json
host: testserver
user-agent: overlay-share-fusion/1.0

{
  "email": "analyst@example.com",
  "remember_me": true
}
```

**Response**

```text
HTTP/1.1 200 OK
content-length: 165
content-type: application/json
set-cookie: wd_session=WaFTEUKmAdTpujue96MWqJrr0jpufa383-wCNsJBjeQ; HttpOnly; Max-Age=604799; Path=/; SameSite=lax

{
  "user": {
    "email_hash": "506729b248c4d43123200937f9b162d3cd3c5a0617fbc02ab691e5dda8f56428",
    "expires_at": "2025-11-11T05:04:16.401317+00:00",
    "id": "analyst@example.com"
  }
}
```

### 2. Inspect pseudo session

**Request**

```text
GET /auth/pseudo/session HTTP/1.1
accept: */*
accept-encoding: gzip, deflate
connection: keep-alive
cookie: wd_session=WaFTEUKmAdTpujue96MWqJrr0jpufa383-wCNsJBjeQ
host: testserver
user-agent: overlay-share-fusion/1.0
```

**Response**

```text
HTTP/1.1 200 OK
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

### 3. List available routes

**Request**

```text
GET /routes HTTP/1.1
accept: */*
accept-encoding: gzip, deflate
connection: keep-alive
cookie: wd_session=WaFTEUKmAdTpujue96MWqJrr0jpufa383-wCNsJBjeQ
host: testserver
user-agent: overlay-share-fusion/1.0
```

**Response**

```text
HTTP/1.1 200 OK
content-length: 212
content-type: application/json

{
  "folder": "/",
  "folders": [],
  "routes": [
    {
      "description": "Return a greeting using DuckDB",
      "id": "hello_world",
      "metrics": {
        "avg_latency_ms": 0.0,
        "hits": 0,
        "interactions": 0,
        "rows": 0
      },
      "path": "/hello",
      "title": "Hello world"
    }
  ]
}
```

### 4. Fetch auto-generated form

**Request**

```text
GET /routes/hello_world/schema?name=Overlay+Share+Fusion HTTP/1.1
accept: */*
accept-encoding: gzip, deflate
connection: keep-alive
cookie: wd_session=WaFTEUKmAdTpujue96MWqJrr0jpufa383-wCNsJBjeQ
host: testserver
user-agent: overlay-share-fusion/1.0
```

**Response**

```text
HTTP/1.1 200 OK
content-length: 471
content-type: application/json

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

### 5. Render HTML before overlay

**Request**

```text
GET /hello?format=html_t&name=Overlay+Share+Fusion HTTP/1.1
accept: text/html
accept-encoding: gzip, deflate
connection: keep-alive
cookie: wd_session=WaFTEUKmAdTpujue96MWqJrr0jpufa383-wCNsJBjeQ
host: testserver
user-agent: overlay-share-fusion/1.0
```

**Response**

```text
HTTP/1.1 200 OK
content-length: 5369
content-type: text/html; charset=utf-8
link: <http://testserver/hello?name=Overlay+Share+Fusion&format=arrow_rpc>; rel="data"
vary: Accept
x-limit: 1
x-offset: 0
x-total-rows: 1

<!doctype html><html data-has-top='true'><head><meta charset='utf-8'><link rel='stylesheet' href='/assets/wd/layout.css?v=0.19.2'><link rel='stylesheet' href='/assets/wd/params.css?v=0.19.2'><link rel='stylesheet' href='/assets/wd/multi_select.css?v=0.19.2'><link rel='stylesheet' href='/assets/wd/table.css?v=0.19.2'><link rel='modulepreload' href='/assets/wd/header.js?v=0.19.2'><link rel='modulepreload' href='/assets/wd/params_form.js?v=0.19.2'><link rel='modulepreload' href='/assets/wd/multi_select.js?v=0.19.2'><link rel='modulepreload' href='/assets/wd/table_header.js?v=0.19.2'></head><body data-wd-widgets='header multi_select params'><div class='wd-shell'><header class='wd-top' data-wd-top data-hidden='false' data-collapsed='false'><div class='wd-top-inner'><div class='wd-top-actions'><button type='button' class='wd-top-button wd-top-button--ghost' data-wd-theme-toggle data-dark-label='Use dark theme' data-light-label='Use light theme' data-system-label='System theme ({theme})' data-hint='Click to toggle theme. Alt-click to follow your system preference.' aria-pressed='mixed'>System theme (light)</button><button type='button' class='wd-top-button' data-wd-top-toggle data-hide-label='Hide header' data-show-label='Show header' aria-expanded='true'>Hide header</button><button type='button' class='wd-top-button' data-wd-filters-toggle data-hide-label='Hide filters' data-show-label='Show filters' aria-controls='wd-filters' aria-expanded='true'>Hide filters</button></div><div class='wd-top-sections'><div class='wd-banners'><p class='banner warning'>Development mode – HTTP only</p><p class='banner info'>Errors follow the webbed_duck taxonomy (see docs).</p></div><div class='wd-summary'><p class='result-summary'>Showing 1–1 of 1 rows</p></div><div class='wd-filters' data-wd-filters id='wd-filters'><div class='params-bar'><form method='get' action='?' class='params-form' data-wd-widget='params'><input type='hidden' name='format' value='html_t'/><input type='hidden' name='offset' value='0'/><div class='param-field'><label for='param-name'>Name</label><input type='text' id='param-name' name='name' value='Overlay Share Fusion' placeholder='Your teammate'/><p class='param-help'>Type a name and press Apply to refresh the greeting</p></div><div class='param-field'><label for='param-greeting_length-toggle'>Greeting length</label><div class='wd-multi-select' data-wd-widget='multi'><button type='button' id='param-greeting_length-toggle' class='wd-multi-select-toggle' aria-haspopup='listbox' aria-expanded='false' aria-controls='param-greeting_length-panel'><span class='wd-multi-select-summary'>All values</span><span class='wd-multi-select-caret' aria-hidden='true'>▾</span></button><div class='wd-multi-select-panel' id='param-greeting_length-panel' role='listbox' aria-multiselectable='true' hidden><div class='wd-multi-select-search'><input type='search' placeholder='Filter options' aria-label='Filter options' autocomplete='off'/></div><p class='wd-multi-select-hint'>Selections stay checked as you filter.</p><ul class='wd-multi-select-options'><li class='wd-multi-select-option' data-search=' '><label><input type='checkbox' value=''/><span></span></label></li><li class='wd-multi-select-option' data-search='28 28'><label><input type='checkbox' value='28'/><span>28</span></label></li></ul><div class='wd-multi-select-actions'><button type='button' class='wd-multi-select-clear'>Clear</button></div></div><select id='param-greeting_length' name='greeting_length' class='wd-multi-select-input' multiple data-placeholder='All values'><option value=''></option><option value='28'>28</option></select></div></div><div class='param-actions'><button type='submit'>Apply</button><a class='reset-link' href='?'>Reset</a></div></form></div></div></div></div></header><main class='wd-main'><div class='wd-main-inner'><div class='wd-chart-block'><svg viewBox='0 0 400 160' role='img' aria-label='Line chart'><polyline fill='none' stroke='#3b82f6' stroke-width='2' points='12.0,80.0'/></svg></div><div class='wd-surface wd-surface--flush wd-table' data-wd-table><div class='wd-table-mini' data-wd-table-mini hidden><span class='wd-table-mini-label'>greeting</span><span class='wd-table-mini-label'>note</span><span class='wd-table-mini-label'>greeting_length</span><span class='wd-table-mini-label'>created_at</span></div><div class='wd-table-scroller'><table><thead><tr><th>greeting</th><th>note</th><th>greeting_length</th><th>created_at</th></tr></thead><tbody><tr><td>Hello, Overlay Share Fusion!</td><td>Personalized greeting rendered by DuckDB</td><td>28</td><td>2025-11-04T05:04:16.306972+00:00</td></tr></tbody></table></div></div><div class='rpc-actions'><a class='rpc-download' href='http://testserver/hello?name=Overlay+Share+Fusion&amp;format=arrow_rpc'>Download this slice (Arrow)</a></div><script type='application/json' id='wd-rpc-config'>{"format":"arrow_rpc","total_rows":1,"offset":0,"limit":null,"page_rows":1,"endpoint":"http://testserver/hello?name=Overlay+Share+Fusion&format=arrow_rpc"}</script></div></main></div><script type='module' src='/assets/wd/header.js?v=0.19.2'></script><script type='module' src='/assets/wd/params_form.js?v=0.19.2'></script><script type='module' src='/assets/wd/multi_select.js?v=0.19.2'></script><script type='module' src='/assets/wd/table_header.js?v=0.19.2'></script></body></html>
```

### 6. Submit overlay note

**Request**

```text
POST /routes/hello_world/overrides HTTP/1.1
accept: */*
accept-encoding: gzip, deflate
connection: keep-alive
content-length: 216
content-type: application/json
cookie: wd_session=WaFTEUKmAdTpujue96MWqJrr0jpufa383-wCNsJBjeQ
host: testserver
user-agent: overlay-share-fusion/1.0

{
  "author": "demo.generator@company.local",
  "column": "note",
  "reason": "Captured by overlay-share-fusion demo",
  "row_key": "{\"greeting\": \"Hello, Overlay Share Fusion!\"}",
  "value": "Notebook insight promoted to the share"
}
```

**Response**

```text
HTTP/1.1 200 OK
content-length: 365
content-type: application/json

{
  "override": {
    "author_hash": "4c328170073b990ae3d2139a21dc3191035081ff08f4132d4abe01c72f5c2fef",
    "author_user_id": "analyst@example.com",
    "column": "note",
    "created_ts": 1762232656.503361,
    "reason": "Captured by overlay-share-fusion demo",
    "route_id": "hello_world",
    "row_key": "{\"greeting\": \"Hello, Overlay Share Fusion!\"}",
    "value": "Notebook insight promoted to the share"
  }
}
```

### 7. Render HTML with overlay applied

**Request**

```text
GET /hello?format=html_t&name=Overlay+Share+Fusion HTTP/1.1
accept: text/html
accept-encoding: gzip, deflate
connection: keep-alive
cookie: wd_session=WaFTEUKmAdTpujue96MWqJrr0jpufa383-wCNsJBjeQ
host: testserver
user-agent: overlay-share-fusion/1.0
```

**Response**

```text
HTTP/1.1 200 OK
content-length: 5367
content-type: text/html; charset=utf-8
link: <http://testserver/hello?name=Overlay+Share+Fusion&format=arrow_rpc>; rel="data"
vary: Accept
x-limit: 1
x-offset: 0
x-total-rows: 1

<!doctype html><html data-has-top='true'><head><meta charset='utf-8'><link rel='stylesheet' href='/assets/wd/layout.css?v=0.19.2'><link rel='stylesheet' href='/assets/wd/params.css?v=0.19.2'><link rel='stylesheet' href='/assets/wd/multi_select.css?v=0.19.2'><link rel='stylesheet' href='/assets/wd/table.css?v=0.19.2'><link rel='modulepreload' href='/assets/wd/header.js?v=0.19.2'><link rel='modulepreload' href='/assets/wd/params_form.js?v=0.19.2'><link rel='modulepreload' href='/assets/wd/multi_select.js?v=0.19.2'><link rel='modulepreload' href='/assets/wd/table_header.js?v=0.19.2'></head><body data-wd-widgets='header multi_select params'><div class='wd-shell'><header class='wd-top' data-wd-top data-hidden='false' data-collapsed='false'><div class='wd-top-inner'><div class='wd-top-actions'><button type='button' class='wd-top-button wd-top-button--ghost' data-wd-theme-toggle data-dark-label='Use dark theme' data-light-label='Use light theme' data-system-label='System theme ({theme})' data-hint='Click to toggle theme. Alt-click to follow your system preference.' aria-pressed='mixed'>System theme (light)</button><button type='button' class='wd-top-button' data-wd-top-toggle data-hide-label='Hide header' data-show-label='Show header' aria-expanded='true'>Hide header</button><button type='button' class='wd-top-button' data-wd-filters-toggle data-hide-label='Hide filters' data-show-label='Show filters' aria-controls='wd-filters' aria-expanded='true'>Hide filters</button></div><div class='wd-top-sections'><div class='wd-banners'><p class='banner warning'>Development mode – HTTP only</p><p class='banner info'>Errors follow the webbed_duck taxonomy (see docs).</p></div><div class='wd-summary'><p class='result-summary'>Showing 1–1 of 1 rows</p></div><div class='wd-filters' data-wd-filters id='wd-filters'><div class='params-bar'><form method='get' action='?' class='params-form' data-wd-widget='params'><input type='hidden' name='format' value='html_t'/><input type='hidden' name='offset' value='0'/><div class='param-field'><label for='param-name'>Name</label><input type='text' id='param-name' name='name' value='Overlay Share Fusion' placeholder='Your teammate'/><p class='param-help'>Type a name and press Apply to refresh the greeting</p></div><div class='param-field'><label for='param-greeting_length-toggle'>Greeting length</label><div class='wd-multi-select' data-wd-widget='multi'><button type='button' id='param-greeting_length-toggle' class='wd-multi-select-toggle' aria-haspopup='listbox' aria-expanded='false' aria-controls='param-greeting_length-panel'><span class='wd-multi-select-summary'>All values</span><span class='wd-multi-select-caret' aria-hidden='true'>▾</span></button><div class='wd-multi-select-panel' id='param-greeting_length-panel' role='listbox' aria-multiselectable='true' hidden><div class='wd-multi-select-search'><input type='search' placeholder='Filter options' aria-label='Filter options' autocomplete='off'/></div><p class='wd-multi-select-hint'>Selections stay checked as you filter.</p><ul class='wd-multi-select-options'><li class='wd-multi-select-option' data-search=' '><label><input type='checkbox' value=''/><span></span></label></li><li class='wd-multi-select-option' data-search='28 28'><label><input type='checkbox' value='28'/><span>28</span></label></li></ul><div class='wd-multi-select-actions'><button type='button' class='wd-multi-select-clear'>Clear</button></div></div><select id='param-greeting_length' name='greeting_length' class='wd-multi-select-input' multiple data-placeholder='All values'><option value=''></option><option value='28'>28</option></select></div></div><div class='param-actions'><button type='submit'>Apply</button><a class='reset-link' href='?'>Reset</a></div></form></div></div></div></div></header><main class='wd-main'><div class='wd-main-inner'><div class='wd-chart-block'><svg viewBox='0 0 400 160' role='img' aria-label='Line chart'><polyline fill='none' stroke='#3b82f6' stroke-width='2' points='12.0,80.0'/></svg></div><div class='wd-surface wd-surface--flush wd-table' data-wd-table><div class='wd-table-mini' data-wd-table-mini hidden><span class='wd-table-mini-label'>greeting</span><span class='wd-table-mini-label'>note</span><span class='wd-table-mini-label'>greeting_length</span><span class='wd-table-mini-label'>created_at</span></div><div class='wd-table-scroller'><table><thead><tr><th>greeting</th><th>note</th><th>greeting_length</th><th>created_at</th></tr></thead><tbody><tr><td>Hello, Overlay Share Fusion!</td><td>Notebook insight promoted to the share</td><td>28</td><td>2025-11-04T05:04:16.306972+00:00</td></tr></tbody></table></div></div><div class='rpc-actions'><a class='rpc-download' href='http://testserver/hello?name=Overlay+Share+Fusion&amp;format=arrow_rpc'>Download this slice (Arrow)</a></div><script type='application/json' id='wd-rpc-config'>{"format":"arrow_rpc","total_rows":1,"offset":0,"limit":null,"page_rows":1,"endpoint":"http://testserver/hello?name=Overlay+Share+Fusion&format=arrow_rpc"}</script></div></main></div><script type='module' src='/assets/wd/header.js?v=0.19.2'></script><script type='module' src='/assets/wd/params_form.js?v=0.19.2'></script><script type='module' src='/assets/wd/multi_select.js?v=0.19.2'></script><script type='module' src='/assets/wd/table_header.js?v=0.19.2'></script></body></html>
```

### 8. Create share with overlay

**Request**

```text
POST /routes/hello_world/share HTTP/1.1
accept: */*
accept-encoding: gzip, deflate
connection: keep-alive
content-length: 182
content-type: application/json
cookie: wd_session=WaFTEUKmAdTpujue96MWqJrr0jpufa383-wCNsJBjeQ
host: testserver
user-agent: overlay-share-fusion/1.0

{
  "columns": [
    "greeting",
    "note",
    "created_at"
  ],
  "emails": [
    "teammate@example.com"
  ],
  "format": "html_t",
  "max_rows": 5,
  "params": {
    "name": "Overlay Share Fusion"
  },
  "redact_columns": [
    "created_at"
  ]
}
```

**Response**

```text
HTTP/1.1 200 OK
content-length: 367
content-type: application/json

{
  "share": {
    "attachments": [],
    "expires_at": "2025-11-04T06:34:16.515217+00:00",
    "format": "html_t",
    "inline_snapshot": true,
    "redacted_columns": [
      "created_at"
    ],
    "rows_shared": 1,
    "token": "kjCCYj5mhTQRlN_IT2bNk8DT7jKMBNqImTUJcIlC2DY",
    "total_rows": 1,
    "url": "http://testserver/shares/kjCCYj5mhTQRlN_IT2bNk8DT7jKMBNqImTUJcIlC2DY",
    "watermark": true,
    "zip_encrypted": false,
    "zipped": false
  }
}
```

### 9. Resolve share token

**Request**

```text
GET /shares/kjCCYj5mhTQRlN_IT2bNk8DT7jKMBNqImTUJcIlC2DY?format=html_t HTTP/1.1
accept: text/html
accept-encoding: gzip, deflate
connection: keep-alive
cookie: wd_session=WaFTEUKmAdTpujue96MWqJrr0jpufa383-wCNsJBjeQ
host: testserver
user-agent: overlay-share-fusion/1.0
```

**Response**

```text
HTTP/1.1 200 OK
content-length: 5290
content-type: text/html; charset=utf-8
link: <http://testserver/shares/kjCCYj5mhTQRlN_IT2bNk8DT7jKMBNqImTUJcIlC2DY?format=arrow_rpc>; rel="data"
vary: Accept
x-limit: 1
x-offset: 0
x-total-rows: 1

<!doctype html><html data-has-top='true'><head><meta charset='utf-8'><link rel='stylesheet' href='/assets/wd/layout.css?v=0.19.2'><link rel='stylesheet' href='/assets/wd/params.css?v=0.19.2'><link rel='stylesheet' href='/assets/wd/multi_select.css?v=0.19.2'><link rel='stylesheet' href='/assets/wd/table.css?v=0.19.2'><link rel='modulepreload' href='/assets/wd/header.js?v=0.19.2'><link rel='modulepreload' href='/assets/wd/params_form.js?v=0.19.2'><link rel='modulepreload' href='/assets/wd/multi_select.js?v=0.19.2'><link rel='modulepreload' href='/assets/wd/table_header.js?v=0.19.2'></head><body data-wd-widgets='header multi_select params'><div class='wd-shell'><header class='wd-top' data-wd-top data-hidden='false' data-collapsed='false'><div class='wd-top-inner'><div class='wd-top-actions'><button type='button' class='wd-top-button wd-top-button--ghost' data-wd-theme-toggle data-dark-label='Use dark theme' data-light-label='Use light theme' data-system-label='System theme ({theme})' data-hint='Click to toggle theme. Alt-click to follow your system preference.' aria-pressed='mixed'>System theme (light)</button><button type='button' class='wd-top-button' data-wd-top-toggle data-hide-label='Hide header' data-show-label='Show header' aria-expanded='true'>Hide header</button><button type='button' class='wd-top-button' data-wd-filters-toggle data-hide-label='Hide filters' data-show-label='Show filters' aria-controls='wd-filters' aria-expanded='true'>Hide filters</button></div><div class='wd-top-sections'><div class='wd-banners'><p class='banner warning'>Development mode – HTTP only</p><p class='banner info'>Errors follow the webbed_duck taxonomy (see docs).</p></div><div class='wd-summary'><p class='result-summary'>Showing 1–1 of 1 rows</p></div><div class='wd-filters' data-wd-filters id='wd-filters'><div class='params-bar'><form method='get' action='?' class='params-form' data-wd-widget='params'><input type='hidden' name='format' value='html_t'/><input type='hidden' name='offset' value='0'/><div class='param-field'><label for='param-name'>Name</label><input type='text' id='param-name' name='name' value='Overlay Share Fusion' placeholder='Your teammate'/><p class='param-help'>Type a name and press Apply to refresh the greeting</p></div><div class='param-field'><label for='param-greeting_length-toggle'>Greeting length</label><div class='wd-multi-select' data-wd-widget='multi'><button type='button' id='param-greeting_length-toggle' class='wd-multi-select-toggle' aria-haspopup='listbox' aria-expanded='false' aria-controls='param-greeting_length-panel'><span class='wd-multi-select-summary'>All values</span><span class='wd-multi-select-caret' aria-hidden='true'>▾</span></button><div class='wd-multi-select-panel' id='param-greeting_length-panel' role='listbox' aria-multiselectable='true' hidden><div class='wd-multi-select-search'><input type='search' placeholder='Filter options' aria-label='Filter options' autocomplete='off'/></div><p class='wd-multi-select-hint'>Selections stay checked as you filter.</p><ul class='wd-multi-select-options'><li class='wd-multi-select-option' data-search=' '><label><input type='checkbox' value=''/><span></span></label></li><li class='wd-multi-select-option' data-search='28 28'><label><input type='checkbox' value='28'/><span>28</span></label></li></ul><div class='wd-multi-select-actions'><button type='button' class='wd-multi-select-clear'>Clear</button></div></div><select id='param-greeting_length' name='greeting_length' class='wd-multi-select-input' multiple data-placeholder='All values'><option value=''></option><option value='28'>28</option></select></div></div><div class='param-actions'><button type='submit'>Apply</button><a class='reset-link' href='?'>Reset</a></div></form></div></div></div></div></header><main class='wd-main'><div class='wd-main-inner'><div class='wd-chart-block'><svg viewBox='0 0 400 160' role='img' aria-label='Line chart'><polyline fill='none' stroke='#3b82f6' stroke-width='2' points='12.0,80.0'/></svg></div><div class='wd-surface wd-surface--flush wd-table' data-wd-table><div class='wd-table-mini' data-wd-table-mini hidden><span class='wd-table-mini-label'>greeting</span><span class='wd-table-mini-label'>note</span><span class='wd-table-mini-label'>greeting_length</span></div><div class='wd-table-scroller'><table><thead><tr><th>greeting</th><th>note</th><th>greeting_length</th></tr></thead><tbody><tr><td>Hello, Overlay Share Fusion!</td><td>Notebook insight promoted to the share</td><td>28</td></tr></tbody></table></div></div><div class='rpc-actions'><a class='rpc-download' href='http://testserver/shares/kjCCYj5mhTQRlN_IT2bNk8DT7jKMBNqImTUJcIlC2DY?format=arrow_rpc'>Download this slice (Arrow)</a></div><script type='application/json' id='wd-rpc-config'>{"format":"arrow_rpc","total_rows":1,"offset":0,"limit":null,"page_rows":1,"endpoint":"http://testserver/shares/kjCCYj5mhTQRlN_IT2bNk8DT7jKMBNqImTUJcIlC2DY?format=arrow_rpc"}</script></div></main></div><script type='module' src='/assets/wd/header.js?v=0.19.2'></script><script type='module' src='/assets/wd/params_form.js?v=0.19.2'></script><script type='module' src='/assets/wd/multi_select.js?v=0.19.2'></script><script type='module' src='/assets/wd/table_header.js?v=0.19.2'></script></body></html>
```

## Auto-form payload from `/routes/{id}/schema`

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

## Local preview after the overlay

```json
[
  {
    "created_at": "2025-11-04T05:04:16.306972+00:00",
    "greeting": "Hello, Overlay Share Fusion!",
    "greeting_length": 28,
    "note": "Notebook insight promoted to the share"
  }
]
```

## Share metadata returned by the server

```json
{
  "artifact": {},
  "attachments": {},
  "share": {
    "attachments": [],
    "expires_at": "2025-11-04T06:34:16.515217+00:00",
    "format": "html_t",
    "inline_snapshot": true,
    "redacted_columns": [
      "created_at"
    ],
    "rows_shared": 1,
    "token": "kjCCYj5mhTQRlN_IT2bNk8DT7jKMBNqImTUJcIlC2DY",
    "total_rows": 1,
    "url": "http://testserver/shares/kjCCYj5mhTQRlN_IT2bNk8DT7jKMBNqImTUJcIlC2DY",
    "watermark": true,
    "zip_encrypted": false,
    "zipped": false
  }
}
```

## Share HTML excerpt

```html
<!doctype html><html data-has-top='true'><head><meta charset='utf-8'><link rel='stylesheet' href='/assets/wd/layout.css?v=0.19.2'><link rel='stylesheet' href='/assets/wd/params.css?v=0.19.2'><link rel='stylesheet' href='/assets/wd/multi_select.css?v=0.19.2'><link rel='stylesheet' href='/assets/wd/table.css?v=0.19.2'><link rel='modulepreload' href='/assets/wd/header.js?v=0.19.2'><link rel='modulepreload' href='/assets/wd/params_form.js?v=0.19.2'><link rel='modulepreload' href='/assets/wd/multi_select.js?v=0.19.2'><link rel='modulepreload' href='/assets/wd/table_header.js?v=0.19.2'></head><body data-wd-widgets='header multi_select params'><div class='wd-shell'><header class='wd-top' data-wd-top data-hidden='false' data-collapsed='false'><div class='wd-top-inner'><div class='wd-top-actions'><button type='button' class='wd-top-button wd-top-button--ghost' data-wd-theme-toggle data-dark-label='Use dark theme' data-light-label='Use light theme' data-system-label='System theme ({theme})' data-hint='Click to toggle theme. Alt-click to follow your system preference.' aria-pressed='mixed'>System theme (light)</button><button type='button' class='wd-top-button' data-wd-top-toggle data-hide-label='Hide header' data-show-label='Show header' aria-expanded='true'>Hide header</button><button type='button' class='wd-top-button' data-wd-filters-toggle data-hide-label='Hide filters' data-show-label='Show filters' aria-controls='wd-filters' aria-expanded='true'>Hide filters</button></div><div class='wd-top-sections'><div class='wd-banners'><p class='banner warning'>Development mode – HTTP only</p><p class='banner info'>Errors follow the webbed_duck taxonomy (see docs).</p></div><div class='wd-summary'><p class='result-summary'>Showing 1–1 of 1 rows</p></div><div class='wd-filters' data-wd-filters id='wd-filters'><div class='params-bar'><form method='get' action='?' class='params-form' data-wd-widget='params'><input type='hidden' name='format' value='html_t'/><input type='hidden' name='offset' value='0'/><div class='param-field'><label for='param-name'>Name</label><input type='text' id='param-name' name='name' value='Overlay Share Fusion' placeholder='Your teammate'/><p class='param-help'>Type a name and press Apply to refresh the greeting</p></div><div class='param-field'><label for='param-greeting_length-toggle'>Greeting length</label><div class='wd-multi-select' data-wd-widget='multi'><button type='button' id='param-greeting_length-toggle' class='wd-multi-select-toggle' aria-haspopup='listbox' aria-expanded='false' aria-controls='param-greeting_length-panel'><span class='wd-multi-select-summary'>All values</span><span class='wd-multi-select-caret' aria-hidden='true'>▾</span></button><div class='wd-multi-select-panel' id='param-greeting_length-panel' role='listbox' aria-multiselectable='true' hidden><div class='wd-multi-select-search'><input type='search' placeholder='Filter options' aria-label='Filter options' autocomplete='off'/></div><p class='wd-multi-select-hint'>Selections stay checked as you filter.</p><ul class='wd-multi-select-options'><li class='wd-multi-select-option' data-search=' '><label><input type='checkbox' value=''/><span></span></label></li><li class='wd-multi-select-option' data-search='28 28'><label><input type='checkbox' value='28'/><span>28</span></label></li></ul><div class='wd-multi-select-actions'><button type='button' class='wd-multi-select-clear'>Clear</button></div></div><select id='param-greeting_length' name='greeting_length' class='wd-multi-select-input' multiple data-placeholder='All values'><option value=''></option><option value='28'>28</option></select></div></div><div class='param-actions'><button type='submit'>Apply</button><a class='reset-link' href='?'>Reset</a></div></form></div></div></div></div></header><main class='wd-main'><div class='wd-main-inner'><div class='wd-chart-block'><svg viewBox='0 0 400 160' role='img' aria-label='Line chart'><polyline fill='none' stroke='#3b82f6' stroke-width='2' points='12.0,80.0'/></svg></div><div class='wd-surface wd-surface--flush wd-table' data-wd-table><div class='wd-table-mini' data-wd-table-mini hidden><span class='wd-table-mini-label'>greeting</span><span class='wd-table-mini-label'>note</span><span class='wd-table-mini-label'>greeting_length</span></div><div class='wd-table-scroller'><table><thead><tr><th>greeting</th><th>note</th><th>greeting_length</th></tr></thead><tbody><tr><td>Hello, Overlay Share Fusion!</td><td>Notebook insight promoted to the share</td><td>28</td></tr></tbody></table></div></div><div class='rpc-actions'><a class='rpc-download' href='http://testserver/shares/kjCCYj5mhTQRlN_IT2bNk8DT7jKMBNqImTUJcIlC2DY?format=arrow_rpc'>Download this slice (Arrow)</a></div><script type='application/json' id='wd-rpc-config'>{"format":"arrow_rpc","total_rows":1,"offset":0,"limit":null,"page_rows":1,"endpoint":"http://testserver/shares/kjCCYj5mhTQRlN_IT2bNk8DT7jKMBNqImTUJcIlC2DY?format=arrow_rpc"}</script></div></main></div><script type='module' src='/assets/wd/header.js?v=0.19.2'></script><script type='module' src='/assets/wd/params_form.js?v=0.19.2'></script><script type='module' src='/assets/wd/multi_select.js?v=0.19.2'></script><script type='module' src='/assets/wd/table_header.js?v=0.19.2'></script></body></html>
```

## Cleanup summary

Removed overlay record from storage
Deleted share record from meta store
Deleted session record from meta store
