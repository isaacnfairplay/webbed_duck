# Route Authoring & Serving Demo

_Auto-generated on 2025-11-04T02:49:58.936447+00:00Z_

## Environment

- Python: 3.12.10 (main, Aug 28 2025, 21:54:05) [GCC 13.3.0]
- webbed_duck version: 0.15.0

## Compile step

Command: `/root/.pyenv/versions/3.12.10/bin/python -m webbed_duck.cli compile --source /workspace/webbed_duck/routes_src --build /workspace/webbed_duck/routes_build`

Return code: 0

Duration: 0.88 s

### stdout

```
Compiled 1 route(s) to /workspace/webbed_duck/routes_build
```

### stderr

```
(empty)
```

## Serve step

Command: `/root/.pyenv/versions/3.12.10/bin/python -m webbed_duck.cli serve --no-watch --no-auto-compile --build /workspace/webbed_duck/routes_build --config /workspace/webbed_duck/config.toml --host 127.0.0.1 --port 8765`

Return code: 0

Duration: 1.49 s

### stdout

```
INFO:     127.0.0.1:53874 - "GET /routes HTTP/1.1" 200 OK
INFO:     127.0.0.1:53888 - "GET /hello?name=Ada&format=html_t HTTP/1.1" 200 OK
INFO:     127.0.0.1:53890 - "GET /hello?name=Ada&format=csv HTTP/1.1" 200 OK
INFO:     127.0.0.1:53898 - "GET /hello?name=Ada&format=arrow HTTP/1.1" 200 OK
```

### stderr

```
INFO:     Started server process [5236]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8765 (Press CTRL+C to quit)
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [5236]
```

## HTTP walkthrough

### HTML (table)

`GET http://127.0.0.1:8765/hello?name=Ada&format=html_t`

Status: 200 OK

Elapsed: 55.09 ms

Content-Type: text/html; charset=utf-8

```
<!doctype html><html data-has-top='true'><head><meta charset='utf-8'><link rel='stylesheet' href='/assets/wd/layout.css?v=0.15.0'><link rel='stylesheet' href='/assets/wd/params.css?v=0.15.0'><link rel='stylesheet' href='/assets/wd/multi_select.css?v=0.15.0'><link rel='stylesheet' href='/assets/wd/table.css?v=0.15.0'><link rel='modulepreload' href='/assets/wd/header.js?v=0.15.0'><link rel='modulepreload' href='/assets/wd/params_form.js?v=0.15.0'><link rel='modulepreload' href='/assets/wd/multi_select.js?v=0.15.0'><link rel='modulepreload' href='/assets/wd/table_header.js?v=0.15.0'></head><body data-wd-widgets='header multi_select params'><div class='wd-shell'><header class='wd-top' data-wd-top data-hidden='false' data-collapsed='false'><div class='wd-top-inner'><div class='wd-top-actions'><button type='button' class='wd-top-button wd-top-button--ghost' data-wd-theme-toggle data-dark-label='Use dark theme' data-light-label='Use light theme' data-system-label='System theme ({theme})' data-hint='Click to toggle theme. Alt-click to follow your system preference.' aria-pressed='mixed'>System theme (light)</button><button type='button' class='wd-top-button' data-wd-top-toggle data-hide-label='Hide header' data-show-label='Show header' aria-expanded='true'>Hide header</button><button type='button' class='wd-top-button' data-wd-filters-toggle data-hide-label='Hide filters' data-show-label='Show filters' aria-controls='wd-filters' aria-expanded='true'>Hide filters</button></div><div class='wd-top-sections'><div class='wd-banners'><p class='banner warning'>Development mode – HTTP only</p><p class='banner info'>Errors follow the webbed_duck taxonomy (see docs).</p></div><div class='wd-summary'><p class='result-summary'>Showing 1–1 of 1 rows</p></div><div class='wd-filters' data-wd-filters id='wd-filters'><div class='params-bar'><form method='get' action='?' class='params-form' data-wd-widget='params'><input type='hidden' name='format' value='html_t'/><input type='hidden' name='offset' value='0'/><div class='param-field'><label for='param-name'>Name</label><input type='text' id='param-name' name='name' value='Ada' placeholder='Your teammate'/><p class='param-help'>Type a name and press Apply to refresh the greeting</p></div><div class='param-actions'><button type='submit'>Apply</button><a class='reset-link' href='?'>Reset</a></div></form></div></div></div></div></header><main class='wd-main'><div class='wd-main-inner'><div class='wd-chart-block'><svg viewBox='0 0 400 160' role='img' aria-label='Line chart'><polyline fill='none' stroke='#3b82f6' stroke-width='2' points='12.0,80.0'/></svg></div><div class='wd-surface wd-surface--flush wd-table' data-wd-table><div class='wd-table-mini' data-wd-table-mini hidden><span class='wd-table-mini-label'>greeting</span><span class='wd-table-mini-label'>note</span><span class='wd-table-mini-label'>greeting_length</span><span class='wd-table-mini-label'>created_at</span></div><div class='wd-table-scroller'><table><thead><tr><th>greeting</th><th>note</th><th>greeting_length</th><th>created_at</th></tr></thead><tbody><tr><td>Hello, Ada!</td><td>Personalized greeting rendered by DuckDB</td><td>11</td><td>2025-11-04T02:50:00.934845+00:00</td></tr></tbody></table></div></div><div class='rpc-actions'><a class='rpc-download' href='http://127.0.0.1:8765/hello?name=Ada&amp;format=arrow_rpc'>Download this slice (Arrow)</a></div><script type='application/json' id='wd-rpc-config'>{"format":"arrow_rpc","total_rows":1,"offset":0,"limit":null,"page_rows":1,"endpoint":"http://127.0.0.1:8765/hello?name=Ada&format=arrow_rpc"}</script></div></main></div><script type='module' src='/assets/wd/header.js?v=0.15.0'></script><script type='module' src='/assets/wd/params_form.js?v=0.15.0'></script><script type='module' src='/assets/wd/multi_select.js?v=0.15.0'></script><script type='module' src='/assets/wd/table_header.js?v=0.15.0'></script></body></html>
```

### CSV download

`GET http://127.0.0.1:8765/hello?name=Ada&format=csv`

Status: 200 OK

Elapsed: 18.35 ms

Content-Type: text/csv; charset=utf-8

```
"greeting","note","greeting_length","created_at"
"Hello, Ada!","Personalized greeting rendered by DuckDB",11,2025-11-04 02:50:00.934845+0000
```

### Arrow stream

`GET http://127.0.0.1:8765/hello?name=Ada&format=arrow`

Status: 200 OK

Elapsed: 6.28 ms

Content-Type: application/vnd.apache.arrow.stream

| greeting | note | greeting_length | created_at |
| --- | --- | --- | --- |
| Hello, Ada! | Personalized greeting rendered by DuckDB | 11 | 2025-11-04T02:50:00.934845+00:00 |

## Build artifacts

| Path | Size (bytes) |
| --- | ---: |
| __pycache__/hello.cpython-312.pyc | 2128 |
| hello.py | 2649 |

## Storage artifacts

| Path | Size (bytes) |
| --- | ---: |
| cache/hello_world/6a56c81c056f7d166ab1da36ddf4adfd36d821b185ce65208c5038b0038ce005/meta.json | 758 |
| cache/hello_world/6a56c81c056f7d166ab1da36ddf4adfd36d821b185ce65208c5038b0038ce005/page-00000.parquet | 1521 |
| runtime/meta.sqlite3 | 32768 |

---

_End of demo._
