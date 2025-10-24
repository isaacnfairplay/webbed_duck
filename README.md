# webbed_duck

`webbed_duck` turns Markdown + SQL route files into HTTP endpoints powered by DuckDB. The 0.3 release wraps a deterministic compiler, a FastAPI runtime, and a pluggable overlay/share system into a single workflow for building intranet dashboards and APIs that stay auditable.

## Highlights

* **Markdown + SQL compiler** – Each `*.sql.md` file is parsed into a Python manifest with strongly-typed parameter metadata, preprocess hooks, postprocessors, chart definitions, and append destinations.
* **Per-request DuckDB execution** – The runtime opens a fresh DuckDB connection for every request, applies trusted preprocessors, and emits Arrow-backed responses that can be rendered as JSON, HTML tables (`html_t`), card grids (`html_c`), feeds, or Arrow stream slices for virtualized UIs.
* **Overlay-aware viewers** – Routes can expose `/routes/{id}/overrides` and `/routes/{id}/append` endpoints to manage inline annotations and CSV-backed append flows, while `/routes/{id}/schema` returns form metadata generated from the compiled manifest.
* **Shares and analytics** – `/shares` turns a route result into downloadable HTML, CSV, or Parquet artifacts (optionally ZIP-encrypted) and logs the request in the runtime store. Popularity analytics and folder indexes use the same metadata to provide lightweight observability.
* **Configurable auth adapters** – Pseudo-auth tokens, basic auth, or custom adapters are resolved via configuration. Tokens and share secrets are hashed on disk with optional user-agent or IP-prefix binding.
* **CLI for every stage** – `webbed_duck.cli` exposes `compile`, `serve`, and `run-incremental` commands so routes can be compiled ahead of deployment, served locally, or executed in resumable cursor batches.

See [`routes_src/hello.sql.md`](routes_src/hello.sql.md) for a fully annotated example route covering params, overrides, append destinations, and chart definitions.

## Storage model

Runtime behavior revolves around a `storage_root` directory declared in `config.toml`:

```
storage_root/
  routes_build/            # compiled manifests (imported by the server)
  cache/                   # materialized CSV/Parquet/HTML artifacts
  schemas/                 # cached Arrow schemas per route
  runtime/
    meta.sqlite3           # sessions, shares, analytics events
    checkpoints.duckdb     # incremental runner state
    auth.duckdb            # pseudo/basic auth reference adapter
  static/                  # compiled CSS/JS and image assets
```

The repository mirrors this separation: `routes_src/` contains authoring assets, `routes_build/` contains the compiled artifacts, and the `webbed_duck/` package houses the compiler, runtime server, and plugins.

## Configuration

`config.toml` drives runtime behavior. The default included with the repo is minimal:

```toml
[server]
storage_root = "storage"
theme = "system"
host = "127.0.0.1"
port = 8000
```

Additional sections can declare auth modes, share behavior, analytics weighting, or asset resolvers as documented in [`AGENTS.md`](AGENTS.md). Because the compiler bakes configuration-sensitive metadata into each manifest, update the config and recompile before deploying changes.

## Usage

Compile routes:

```bash
python -m webbed_duck.cli compile --source routes_src --build routes_build
```

Run the development server (requires the compiled routes):

```bash
python -m webbed_duck.cli serve --build routes_build --config config.toml
```

Visit `http://127.0.0.1:8000/hello?name=DuckDB` to exercise the sample route. Append `&format=html_c` or `&format=feed` to see the HTML viewers, or `&format=arrow&limit=25` for Arrow RPC slices. Use `POST /routes/hello/overrides` to annotate rows, `POST /routes/hello/append` to persist CSV records, and `GET /routes/hello/schema` to generate auto-form metadata.

To create shareable artifacts, call `POST /shares` with a `route_id`, desired `format`, and optional attachment preferences. The server records share metadata in SQLite, renders requested attachments (CSV, Parquet, HTML), and can watermark inline HTML when configured. Download tokens inherit the same hashing and optional client-binding rules as pseudo-auth sessions.

The incremental runner is available for long-lived cursor workloads:

```bash
python -m webbed_duck.cli run-incremental --route-id hello_world --build routes_build \
  --config config.toml --cursor-column created_at
```

It persists per-route progress in `runtime/checkpoints.duckdb` so resumable extractions can pick up where the previous invocation left off.

## Encrypted ZIP attachments

Shares can optionally bundle CSV, Parquet, or HTML artifacts into a ZIP archive. If a share request specifies a `zip_passphrase`, webbed_duck encrypts the archive with AES via the optional [`pyzipper`](https://pypi.org/project/pyzipper/) dependency. Install it with:

```bash
pip install pyzipper
```

When `pyzipper` is not installed the server still produces plain ZIP archives and reports `"zip_encrypted": false` in the share metadata. Passphrase requests are rejected in this scenario so teams that require encryption can surface the missing dependency quickly.

## Development

Run the tests locally before sending changes:

```bash
pytest
```

The suite exercises the Markdown compiler, preprocess execution, pseudo-share workflows, overlay storage, and analytics aggregation. Adding new features should include accompanying tests so compiled routes, runtime adapters, and plugins remain stable.
