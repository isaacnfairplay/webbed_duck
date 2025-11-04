# Route Authoring & Serving Demo

_Auto-generated on 2025-11-04T03:21:53.885365+00:00Z_

## Environment

- Python: 3.12.10 (main, Aug 28 2025, 21:54:05) [GCC 13.3.0]
- webbed_duck version: 0.19.1

## Compile step

Command: `/root/.pyenv/versions/3.12.10/bin/python -m webbed_duck.cli compile --source /workspace/webbed_duck/routes_src --build /workspace/webbed_duck/routes_build`

Return code: 0

Duration: 1.55 s

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

Duration: 1.59 s

### stdout

```
INFO:     127.0.0.1:43990 - "GET /routes HTTP/1.1" 200 OK
INFO:     127.0.0.1:43992 - "GET /hello?name=Ada&format=html_t HTTP/1.1" 200 OK
INFO:     127.0.0.1:44004 - "GET /hello?name=Ada&format=csv HTTP/1.1" 200 OK
INFO:     127.0.0.1:44020 - "GET /hello?name=Ada&format=arrow HTTP/1.1" 200 OK
```

### stderr

```
INFO:     Started server process [5697]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8765 (Press CTRL+C to quit)
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [5697]
```

## HTTP walkthrough

### HTML (table)

`GET http://127.0.0.1:8765/hello?name=Ada&format=html_t`

Status: 200 OK

Elapsed: 59.24 ms

Content-Type: text/html; charset=utf-8

<details>
<summary>View HTML source</summary>

```html
<!doctype html><html data-has-top='true'><head><meta charset='utf-8'><link rel='stylesheet' href='/assets/wd/layout.css?v=0.19.1'><link rel='stylesheet' href='/assets/wd/params.css?v=0.19.1'><link rel='stylesheet' href='/assets/wd/multi_select.css?v=0.19.1'><link rel='stylesheet' href='/assets/wd/table.css?v=0.19.1'><link rel='modulepreload' href='/assets/wd/header.js?v=0.19.1'><link rel='modulepreload' href='/assets/wd/params_form.js?v=0.19.1'><link rel='modulepreload' href='/assets/wd/multi_select.js?v=0.19.1'><link rel='modulepreload' href='/assets/wd/table_header.js?v=0.19.1'></head><body data-wd-widgets='header multi_select params'><div class='wd-shell'><header class='wd-top' data-wd-top data-hidden='false' data-collapsed='false'><div class='wd-top-inner'><div class='wd-top-actions'><button type='button' class='wd-top-button wd-top-button--ghost' data-wd-theme-toggle data-dark-label='Use dark theme' data-light-label='Use light theme' data-system-label='System theme ({theme})' data-hint='Click to toggle theme. Alt-click to follow your system preference.' aria-pressed='mixed'>System theme (light)</button><button type='button' class='wd-top-button' data-wd-top-toggle data-hide-label='Hide header' data-show-label='Show header' aria-expanded='true'>Hide header</button><button type='button' class='wd-top-button' data-wd-filters-toggle data-hide-label='Hide filters' data-show-label='Show filters' aria-controls='wd-filters' aria-expanded='true'>Hide filters</button></div><div class='wd-top-sections'><div class='wd-banners'><p class='banner warning'>Development mode – HTTP only</p><p class='banner info'>Errors follow the webbed_duck taxonomy (see docs).</p></div><div class='wd-summary'><p class='result-summary'>Showing 1–1 of 1 rows</p></div><div class='wd-filters' data-wd-filters id='wd-filters'><div class='params-bar'><form method='get' action='?' class='params-form' data-wd-widget='params'><input type='hidden' name='format' value='html_t'/><input type='hidden' name='offset' value='0'/><div class='param-field'><label for='param-name'>Name</label><input type='text' id='param-name' name='name' value='Ada' placeholder='Your teammate'/><p class='param-help'>Type a name and press Apply to refresh the greeting</p></div><div class='param-field'><label for='param-greeting_length-toggle'>Greeting length</label><div class='wd-multi-select' data-wd-widget='multi'><button type='button' id='param-greeting_length-toggle' class='wd-multi-select-toggle' aria-haspopup='listbox' aria-expanded='false' aria-controls='param-greeting_length-panel'><span class='wd-multi-select-summary'>All values</span><span class='wd-multi-select-caret' aria-hidden='true'>▾</span></button><div class='wd-multi-select-panel' id='param-greeting_length-panel' role='listbox' aria-multiselectable='true' hidden><div class='wd-multi-select-search'><input type='search' placeholder='Filter options' aria-label='Filter options' autocomplete='off'/></div><p class='wd-multi-select-hint'>Selections stay checked as you filter.</p><ul class='wd-multi-select-options'><li class='wd-multi-select-option' data-search=' '><label><input type='checkbox' value=''/><span></span></label></li><li class='wd-multi-select-option' data-search='11 11'><label><input type='checkbox' value='11'/><span>11</span></label></li></ul><div class='wd-multi-select-actions'><button type='button' class='wd-multi-select-clear'>Clear</button></div></div><select id='param-greeting_length' name='greeting_length' class='wd-multi-select-input' multiple data-placeholder='All values'><option value=''></option><option value='11'>11</option></select></div></div><div class='param-actions'><button type='submit'>Apply</button><a class='reset-link' href='?'>Reset</a></div></form></div></div></div></div></header><main class='wd-main'><div class='wd-main-inner'><div class='wd-chart-block'><svg viewBox='0 0 400 160' role='img' aria-label='Line chart'><polyline fill='none' stroke='#3b82f6' stroke-width='2' points='12.0,80.0'/></svg></div><div class='wd-surface wd-surface--flush wd-table' data-wd-table><div class='wd-table-mini' data-wd-table-mini hidden><span class='wd-table-mini-label'>greeting</span><span class='wd-table-mini-label'>note</span><span class='wd-table-mini-label'>greeting_length</span><span class='wd-table-mini-label'>created_at</span></div><div class='wd-table-scroller'><table><thead><tr><th>greeting</th><th>note</th><th>greeting_length</th><th>created_at</th></tr></thead><tbody><tr><td>Hello, Ada!</td><td>Personalized greeting rendered by DuckDB</td><td>11</td><td>2025-11-04T03:21:56.641628+00:00</td></tr></tbody></table></div></div><div class='rpc-actions'><a class='rpc-download' href='http://127.0.0.1:8765/hello?name=Ada&amp;format=arrow_rpc'>Download this slice (Arrow)</a></div><script type='application/json' id='wd-rpc-config'>{"format":"arrow_rpc","total_rows":1,"offset":0,"limit":null,"page_rows":1,"endpoint":"http://127.0.0.1:8765/hello?name=Ada&format=arrow_rpc"}</script></div></main></div><script type='module' src='/assets/wd/header.js?v=0.19.1'></script><script type='module' src='/assets/wd/params_form.js?v=0.19.1'></script><script type='module' src='/assets/wd/multi_select.js?v=0.19.1'></script><script type='module' src='/assets/wd/table_header.js?v=0.19.1'></script></body></html>
```

</details>

<div class="demo-preview" data-source="GET http://127.0.0.1:8765/hello?name=Ada&amp;format=html_t">
<div class='wd-shell'><header class='wd-top' data-wd-top data-hidden='false' data-collapsed='false'><div class='wd-top-inner'><div class='wd-top-actions'><button type='button' class='wd-top-button wd-top-button--ghost' data-wd-theme-toggle data-dark-label='Use dark theme' data-light-label='Use light theme' data-system-label='System theme ({theme})' data-hint='Click to toggle theme. Alt-click to follow your system preference.' aria-pressed='mixed'>System theme (light)</button><button type='button' class='wd-top-button' data-wd-top-toggle data-hide-label='Hide header' data-show-label='Show header' aria-expanded='true'>Hide header</button><button type='button' class='wd-top-button' data-wd-filters-toggle data-hide-label='Hide filters' data-show-label='Show filters' aria-controls='wd-filters' aria-expanded='true'>Hide filters</button></div><div class='wd-top-sections'><div class='wd-banners'><p class='banner warning'>Development mode – HTTP only</p><p class='banner info'>Errors follow the webbed_duck taxonomy (see docs).</p></div><div class='wd-summary'><p class='result-summary'>Showing 1–1 of 1 rows</p></div><div class='wd-filters' data-wd-filters id='wd-filters'><div class='params-bar'><form method='get' action='?' class='params-form' data-wd-widget='params'><input type='hidden' name='format' value='html_t'/><input type='hidden' name='offset' value='0'/><div class='param-field'><label for='param-name'>Name</label><input type='text' id='param-name' name='name' value='Ada' placeholder='Your teammate'/><p class='param-help'>Type a name and press Apply to refresh the greeting</p></div><div class='param-field'><label for='param-greeting_length-toggle'>Greeting length</label><div class='wd-multi-select' data-wd-widget='multi'><button type='button' id='param-greeting_length-toggle' class='wd-multi-select-toggle' aria-haspopup='listbox' aria-expanded='false' aria-controls='param-greeting_length-panel'><span class='wd-multi-select-summary'>All values</span><span class='wd-multi-select-caret' aria-hidden='true'>▾</span></button><div class='wd-multi-select-panel' id='param-greeting_length-panel' role='listbox' aria-multiselectable='true' hidden><div class='wd-multi-select-search'><input type='search' placeholder='Filter options' aria-label='Filter options' autocomplete='off'/></div><p class='wd-multi-select-hint'>Selections stay checked as you filter.</p><ul class='wd-multi-select-options'><li class='wd-multi-select-option' data-search=' '><label><input type='checkbox' value=''/><span></span></label></li><li class='wd-multi-select-option' data-search='11 11'><label><input type='checkbox' value='11'/><span>11</span></label></li></ul><div class='wd-multi-select-actions'><button type='button' class='wd-multi-select-clear'>Clear</button></div></div><select id='param-greeting_length' name='greeting_length' class='wd-multi-select-input' multiple data-placeholder='All values'><option value=''></option><option value='11'>11</option></select></div></div><div class='param-actions'><button type='submit'>Apply</button><a class='reset-link' href='?'>Reset</a></div></form></div></div></div></div></header><main class='wd-main'><div class='wd-main-inner'><div class='wd-chart-block'><svg viewBox='0 0 400 160' role='img' aria-label='Line chart'><polyline fill='none' stroke='#3b82f6' stroke-width='2' points='12.0,80.0'/></svg></div><div class='wd-surface wd-surface--flush wd-table' data-wd-table><div class='wd-table-mini' data-wd-table-mini hidden><span class='wd-table-mini-label'>greeting</span><span class='wd-table-mini-label'>note</span><span class='wd-table-mini-label'>greeting_length</span><span class='wd-table-mini-label'>created_at</span></div><div class='wd-table-scroller'><table><thead><tr><th>greeting</th><th>note</th><th>greeting_length</th><th>created_at</th></tr></thead><tbody><tr><td>Hello, Ada!</td><td>Personalized greeting rendered by DuckDB</td><td>11</td><td>2025-11-04T03:21:56.641628+00:00</td></tr></tbody></table></div></div><div class='rpc-actions'><a class='rpc-download' href='http://127.0.0.1:8765/hello?name=Ada&amp;format=arrow_rpc'>Download this slice (Arrow)</a></div></div></main></div>
</div>

### CSV download

`GET http://127.0.0.1:8765/hello?name=Ada&format=csv`

Status: 200 OK

Elapsed: 63.98 ms

Content-Type: text/csv; charset=utf-8

```
"greeting","note","greeting_length","created_at"
"Hello, Ada!","Personalized greeting rendered by DuckDB",11,2025-11-04 03:21:56.641628+0000
```

### Arrow stream

`GET http://127.0.0.1:8765/hello?name=Ada&format=arrow`

Status: 200 OK

Elapsed: 6.31 ms

Content-Type: application/vnd.apache.arrow.stream

| greeting | note | greeting_length | created_at |
| --- | --- | --- | --- |
| Hello, Ada! | Personalized greeting rendered by DuckDB | 11 | 2025-11-04T03:21:56.641628+00:00 |

## Build artifacts

| Path | Size (bytes) |
| --- | ---: |
| __pycache__/hello.cpython-312.pyc | 2266 |
| hello.py | 3042 |

## Storage artifacts

| Path | Size (bytes) |
| --- | ---: |
| cache/hello_world/c15c2c97647c6b421fd9604aaf425c1356b34f803addd959089da19c24632270/meta.json | 951 |
| cache/hello_world/c15c2c97647c6b421fd9604aaf425c1356b34f803addd959089da19c24632270/page-00000.parquet | 1521 |
| runtime/meta.sqlite3 | 32768 |

---

_End of demo._
