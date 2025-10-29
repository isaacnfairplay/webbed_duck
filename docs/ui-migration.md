# UI migration guide

This guide maps the legacy HTML helpers to the refactored layered rendering system introduced in 0.5. The refactor keeps the server-side rendering model intact while moving UI behavior into dedicated modules and static assets.

## Renderer mapping

| Legacy helper | New module | Notes |
| ------------- | ---------- | ----- |
| `webbed_duck.server.postprocess.render_table_html` | `webbed_duck.server.ui.views.table.render_table` | Emits the scroll container, sticky header `<th>`, and table body. Layout-level wrappers now live in `layout.render_layout`. |
| `webbed_duck.server.postprocess.render_cards_html_with_assets` | `webbed_duck.server.ui.views.cards.render_cards` | Produces the card grid DOM; assets are requested through the `[ui]` metadata contract. |
| `webbed_duck.server.postprocess.render_feed_html` | `webbed_duck.server.ui.views.feed.render_feed` | Renders grouped feed entries and defers sticky-header controls to the layout. |
| `webbed_duck.server.postprocess.render_chartjs_html` | `webbed_duck.server.ui.views.charts.render_chart_grid` + `layout.render_layout` | Chart canvases render via `<canvas data-wd-chart="…">` markup, while `layout.render_layout` adds scripts/styles based on route metadata. |
| `_render_params_ui` | `webbed_duck.server.ui.widgets.params.render_params_form` | Builds the filter form (including hidden inputs for pagination and downloads). |
| `_render_multi_select_control` | `webbed_duck.server.ui.widgets.multi_select.render_multi_select` | Owns the multi-select markup and hidden `<select multiple>` element. |
| `_TOP_BAR_SCRIPT` sticky header snippet | `webbed_duck/static/assets/wd/header.js` | Sticky-header behavior now boots from a shared front-end plugin referenced by the `[ui.scripts]` list. |
| `_PARAMS_STYLES`, `_BASE_LAYOUT_STYLES` inline CSS | `webbed_duck/static/assets/wd/*.css` | Styles are split across `layout.css`, `params.css`, `multi_select.css`, `table.css`, `cards.css`, `feed.css`, and `charts.css`. |

## Asset contract

Compiled routes can request widgets, styles, and scripts through the new `[ui]` table in their metadata. The post-processors merge those declarations with renderer defaults and feed them to `layout.resolve_assets`, which:

- deduplicates entries,
- appends `?v={package_version}` cache-busting query parameters,
- emits `<link rel="stylesheet">` and `<script type="module">` tags only once per page.

Example:

```toml
[ui]
widgets = ["header", "params", "multi_select"]
styles  = ["layout", "params", "table"]
scripts = ["header", "multi_select", "chart_boot"]
```

The JavaScript plugins (`header.js`, `multi_select.js`, `params_form.js`, `chart_boot.js`) attach behavior to server-rendered markup using `data-wd-*` attributes. CSS files live alongside them under `webbed_duck/static/assets/wd/`.

## Progressive enhancement

The migration keeps the SSR-first contract:

- Pages remain functional without JavaScript. Filter forms submit as GET requests, and the hidden `<select multiple>` continues to drive submitted query parameters.
- Chart embeds return the vendor `<script src>` tag, the chart grid HTML, and the shared `/assets/wd/chart_boot.js` module so consumers can drop the snippet into other pages without additional boot code.
- RPC and Arrow download links are unchanged—`layout.render_layout` merely positions them within the shell.

## Testing updates

- Unit tests now target the renderer modules directly (see `tests/test_postprocess.py`), verifying structure such as sticky table headers, chart config blocks, and hidden pagination inputs.
- JavaScript plugins expose `init*` helpers that can be tested with DOM-like stubs to assert attribute toggles, summary text updates, and Chart.js bootstrapping without a browser.
- README guidance outlines recommended Playwright/Cypress/Galen coverage for sticky headers, multi-select interactions, responsive cards, and chart rendering.

Migrating bespoke helpers or out-of-tree forks should follow the same pattern: render fragments with the new view/widget modules, declare required assets via `[ui]`, and let `layout.render_layout` assemble the final response.
