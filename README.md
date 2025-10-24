# webbed_duck

## What is webbed_duck?

`webbed_duck` is a self-contained data server that turns declarative `.sql.md` files into live DuckDB-backed web endpoints.

- Each `.sql.md` file is a contract for one route: business context, parameter specification, presentation hints, and the SQL relation itself.
- The compiler translates those contracts into executable Python modules and registers them as HTTP endpoints.
- The runtime ships the results as styled HTML tables or cards, JSON payloads, CSV and Parquet downloads, or Arrow streams—no custom FastAPI or Flask code required.
- Drop `.sql.md` files into a folder, run the bundled CLI, and immediately browse or export the data surfaces.
- Designed for operational, quality, and manufacturing review workflows where trustworthy tables with traceability matter more than bespoke UI code.

## Quick start

1. **Install the package and dependencies.**
   ```bash
   pip install webbed-duck
   ```

2. **Create your route source directory** (default is `routes_src/`) and add `.sql.md` contracts (see [Writing a `.sql.md` route](#writing-a-sqlmd-route)).

3. **Compile the contracts into runnable manifests (optional when auto-compile is enabled).**
   ```bash
   webbed-duck compile --source routes_src --build routes_build
   ```

4. **Launch the server.** The CLI compiles using your configuration defaults and can hot-reload routes while you edit them.
   ```bash
   webbed-duck serve --config config.toml --watch
   ```
   - `--watch` keeps the compiler running and reloads routes in-place when `.sql.md` files change.
   - Pass `--no-auto-compile` to serve pre-built `routes_build/` artifacts without touching the source tree.

5. **Browse the routes.** Open `http://127.0.0.1:8000/hello` (or your route path) in a browser, or request alternate formats with `?format=csv`, `?format=parquet`, etc.

## How it works today (v0.4)

### Runtime startup

- `webbed-duck serve` loads configuration from `config.toml` (defaults to host `127.0.0.1`, port `8000`, storage under `./storage`) and resolves `server.source_dir` / `server.build_dir`.
- With `server.auto_compile = true` (the default) the CLI compiles every `*.sql.md` contract in the configured source directory before starting Uvicorn.
- Enabling watch mode (`server.watch = true` or the `--watch` flag) keeps a background poller running so route edits trigger re-compilation and live reloading without restarting the process.
- The server is a FastAPI application exposed via Uvicorn. No additional framework integration is necessary for development deployments.

### Route discovery and mapping

- The compiler scans the source tree for `*.sql.md` files. Each file must begin with TOML frontmatter between `+++` delimiters.
- Frontmatter declares the route `id`, HTTP `path`, optional `version`, default and allowed formats, parameters, and metadata.
- Compiled artifacts are written to the `--build` directory, mirroring the source folder structure but with `.py` files. These contain serialised `ROUTE` dictionaries consumed at runtime.
- At boot—and after each live reload triggered by the watcher—the server imports every compiled module and registers the route path on the FastAPI app. The `id` doubles as the logical identifier for `/routes/{id}` helper endpoints.

### Parameter binding

- Parameters are declared under `[params.<name>]` in the frontmatter with `type` (`str`, `int`, `float`, or `bool`), `required`, `default`, and `description`.
- Within the SQL block, use `{{name}}` placeholders. During compilation each placeholder becomes a positional `?` parameter to DuckDB, preserving type safety.
- At request time the runtime reads query string values, validates types (including boolean coercion for `true`/`false`, `1`/`0`), applies defaults, and rejects missing required parameters.
- Additional runtime controls:
  - `?limit=` and `?offset=` apply post-query pagination without changing the SQL.
  - `?column=` can be repeated to restrict returned columns.

### Supported outputs

All of the following formats work today, provided the route either allows them explicitly or leaves `allowed_formats` empty (which enables everything):

| Format query       | Response                                                  |
| ------------------ | --------------------------------------------------------- |
| default / `?format=json` | JSON payload with metadata, columns, rows, and latency. |
| `?format=table`    | JSON structured identically to `json` (for compatibility). |
| `?format=html_t`   | Styled HTML table view with optional chart annotations.    |
| `?format=html_c`   | Card-style HTML view honouring `[html_c]` metadata.        |
| `?format=feed`     | Feed-style HTML view for narrative updates.               |
| `?format=csv`      | Streaming CSV download with `text/csv` content type.      |
| `?format=parquet`  | Parquet file stream generated via Apache Arrow.           |
| `?format=arrow`    | Arrow IPC stream for programmatic consumers.              |
| `?format=arrow_rpc`| Arrow IPC stream with pagination headers.                 |

Routes may set `default_format` in frontmatter to choose the response when `?format` is omitted.

### Data sources and execution model

- Every request opens a fresh DuckDB connection, executes the prepared SQL with bound parameters, and immediately closes the connection.
- You can query DuckDB-native sources such as Parquet, CSV, or Iceberg directly inside the SQL (`SELECT * FROM read_parquet('data/orders.parquet')`).
- For derived inputs, register preprocessors in the `.sql.md` file to inject computed parameters (e.g., resolve the latest production date) before SQL execution.
- After execution, server-side overlays (cell-level overrides) and append metadata apply automatically when configured in the contract.
- Analytics (hits, rows, latency, interactions) are tracked per route and exposed via `GET /routes` and `GET /routes/{id}/schema` today.

### Auth, sharing, and append workflows

- Authentication modes are controlled via `config.toml`. The default mode is `none`. Enabling `auth.mode="pseudo"` activates the pseudo-session API (`/auth/pseudo/session`) and share endpoints.
- Users with a pseudo-session can request `/routes/{id}/share` to email HTML/CSV/Parquet snapshots using the configured email adapter.
- Routes that define `[append]` metadata accept JSON payloads at `/routes/{id}/append` to persist rows into CSV logs stored under the configured storage root.

## Writing a `.sql.md` route

A `.sql.md` file is the single source of truth for a route: metadata, parameter definitions, documentation, and SQL live together. The structure is:

1. **Frontmatter (`+++ … +++`):** TOML describing route metadata and behaviour.
2. **Markdown body:** Human-facing documentation explaining the purpose, context, and usage.
3. **SQL code block:** A fenced ```sql``` block containing the relation definition.

### Frontmatter contract

Common keys include:

- `id`: Stable identifier used for compilation, local runners, and helper endpoints.
- `path`: HTTP path to mount (e.g., `/ops/smt/daily`).
- `title`, `description`: Display metadata for HTML responses and route listings.
- `version`: Optional semantic or document version string.
- `default_format`: Default response format when `?format` is not supplied.
- `allowed_formats`: Restricts runtime formats (values from the table above).
- `[params.<name>]`: Parameter declaration blocks with `type`, `required`, `default`, `description`, and arbitrary extra keys.
- Presentation metadata blocks such as `[html_t]`, `[html_c]`, `[feed]`, `[overrides]`, `[append]`, `[charts]`, and `[assets]` configure post-processors, override policies, append targets, charts, and asset lookup hints.
- `[[preprocess]]` entries or `[preprocess]` tables list callables (`module:function` or dotted paths) that massage parameters prior to execution.

### SQL placeholders

- Write DuckDB SQL inside a fenced ```sql``` block.
- Interpolate declared parameters with `{{param_name}}`. The compiler enforces that every placeholder corresponds to a declared parameter and converts it to a bound parameter in the prepared statement.
- Do not concatenate user input manually—let the compiler handle binding to avoid injection risks.

### Example route

```markdown
+++
id = "workstation_line"
path = "/ops/workstations"
title = "Workstation production by line"
description = "Hourly production roll-up with scrap and labour attribution."
default_format = "html_t"
allowed_formats = ["html_t", "csv", "parquet", "json"]

[params.plant_day]
type = "str"
required = true
description = "Production day in YYYY-MM-DD format"

[params.line]
type = "str"
required = false
description = "Optional production line code"

[html_t]
title_col = "line"
meta_cols = ["plant_day", "supervisor"]

[[charts]]
id = "throughput"
type = "line"
x = "hour"
y = "units"
+++

# Workstation line throughput

Use this surface to reconcile hourly throughput, scrap, and labour time.
Parameters are documented above; default charts plot `units` per hour.

```sql
WITH source AS (
  SELECT *
  FROM read_parquet('data/workstations.parquet')
  WHERE plant_day = {{plant_day}}
)
SELECT
  plant_day,
  line,
  hour,
  SUM(units_produced) AS units,
  SUM(scrap_units) AS scrap,
  AVG(labour_hours) AS labour_hours,
  ANY_VALUE(supervisor) AS supervisor
FROM source
WHERE {{line}} IS NULL OR line = {{line}}
GROUP BY ALL
ORDER BY hour;
```
```

This single file defines documentation, parameter validation, output formatting, charts, override rules, and the actual dataset. The compiler consumes it directly—there are no auxiliary `.sql` or `.yaml` files.

## Auto-compile and serve model

- **Default behaviour:** `webbed-duck serve` compiles the configured source directory before launching so you always run with fresh artifacts.
- **Configurable toggles:** Set `server.auto_compile = false` or pass `--no-auto-compile` to serve an existing `routes_build/` snapshot without touching the source tree. Enable `server.watch = true` (or `--watch`) to keep a background watcher running for instant reloads.
- **Configuration surface:** `config.toml` still controls storage (`server.storage_root`), theming, analytics weights, auth mode, email adapter, and share behaviour alongside the new `source_dir` / `build_dir` settings.

## Formats and responses

Each compiled route honours runtime format negotiation:

```bash
# HTML table for people on the floor
curl http://127.0.0.1:8000/ops/workstations?plant_day=2024-03-01

# CSV export for spreadsheets
curl "http://127.0.0.1:8000/ops/workstations?plant_day=2024-03-01&format=csv" -o workstations.csv

# Parquet for analytics pipelines
curl "http://127.0.0.1:8000/ops/workstations?plant_day=2024-03-01&format=parquet" -o workstations.parquet

# JSON payload (default structure)
curl "http://127.0.0.1:8000/ops/workstations?plant_day=2024-03-01&format=json"
```

Routes can further customise behaviour via presentation metadata—e.g., `[html_c]` for card decks, `[feed]` for update feeds, or `[append]` to allow operators to push corrections into CSV append logs.

## MVP 0.4 — One-stop-shop data server

> **Promise:** By 0.4, `webbed_duck` is the standalone app for data surfaces. Drop `.sql.md` files into a folder, start the server, and you get working web endpoints with HTML/CSV/Parquet/JSON output, parameter forms, lightweight auth, and optional cached snapshots. No hand-written FastAPI, no manual HTML, no bespoke export logic—just `.sql.md` contracts.

### Highlights in 0.4

- Auto-compiling `webbed-duck serve` command with config-driven `source_dir` / `build_dir` defaults and a `--no-auto-compile` escape hatch for frozen artifacts.
- Built-in watch mode (`server.watch` / `--watch`) that recompiles `.sql.md` files and hot-reloads FastAPI routes without restarting Uvicorn.
- Dynamic route registry inside the FastAPI app so helpers such as `/routes/{id}` and sharing workflows immediately reflect newly compiled contracts.
- CLI and docs tuned for a zero-config quick start: install, drop a contract in `routes_src/`, and run `webbed-duck serve --config config.toml --watch` to explore.

### Next up (post-0.4)

- Declarative caching / snapshot controls persisted under `storage_root/cache/`.
- Richer auto-generated parameter forms exposed directly in HTML responses.
- Additional auth adapter examples and configuration presets for external identity providers.

MVP 0.4 is the first release we expect to hand to an ops lead with no extra scaffolding.

## Extending webbed_duck

- **Preprocessors:** Register callables (e.g., `myapp.preprocess.resolve_shift_window`) and reference them in frontmatter to derive or validate parameters before the SQL runs.
- **Postprocessors and presentation:** Use `[html_t]`, `[html_c]`, `[feed]`, and `[[charts]]` to pass configuration into the built-in renderers. Custom renderers can be registered via the plugin registries in `webbed_duck.plugins.*`.
- **Assets and overlays:** `[assets]` metadata controls how related images are resolved; `[overrides]` enables per-cell overrides with audit trails managed by the overlay store.
- **Local execution:** `webbed_duck.core.local.run_route("route_id", params={...}, format="arrow")` executes a compiled route entirely in-process, useful for testing or batch jobs.

As the plugin hooks stabilise, expect additional documentation and examples demonstrating custom formatters, enrichment joins, and sharing adapters that slot into the compile/serve lifecycle without forking the framework.

