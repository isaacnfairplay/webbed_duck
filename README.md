# webbed_duck

`webbed_duck` turns Markdown + SQL route files into HTTP endpoints powered by DuckDB.

This MVP (v0.3) extends the core compiler and server with annotation-ready viewers and workflow helpers:

* A Markdown compiler that translates `*.sql.md` files into Python route manifests and preserves per-route metadata for cards,
  feeds, charts, overrides, and append targets.
* A FastAPI-based server that executes DuckDB queries per-request, applies per-cell overrides from the overlay store, and
  returns JSON, HTML table/card/feed views, Arrow streams, and downloadable CSV/Parquet artifacts.
* New endpoints for `/routes/{id}/schema`, `/routes/{id}/overrides`, and `/routes/{id}/append` to expose form metadata, manage
  overrides, and persist CSV append operations.
* Authentication adapters spanning pseudo sessions, proxy headers, and externally supplied factories so intranet deployments can
  align with upstream identity providers.
* Share tokens minted via `POST /shares` and redeemed through `GET /shares/{token}` with hashed secrets, TTL/IP binding, and
  optional email delivery that zips CSV/Parquet attachments through a configurable adapter.
* Popularity analytics, folder indexes, and a pluggable auth adapter resolved via configuration alongside a standalone perf
  harness (`examples/perf_harness.py`) for timing compiled routes without HTTP overhead.
* Command-line tooling for compiling routes, running the development server, iterating cursor-driven workloads via
  `run-incremental`, and benchmarking routes through the perf harness.

See `routes_src/hello.sql.md` for an example route.

## Usage

Compile routes:

```bash
python -m webbed_duck.cli compile --source routes_src --build routes_build
```

Run the development server (requires the compiled routes):

```bash
python -m webbed_duck.cli serve --build routes_build --config config.toml
```

Visit `http://127.0.0.1:8000/hello?name=DuckDB` to exercise the sample route. Append `&format=html_c`, `&format=feed`,
`&format=csv`, or `&format=parquet` to explore the renderers and downloadable artifacts, or `&format=arrow&limit=25` for Arrow
RPC slices. Use `POST /routes/hello/overrides` to annotate rows, `POST /routes/hello/append` to persist CSV records, and `POST
/shares` (optionally with an `email` payload) to mint hashed links and send zipped CSV/Parquet attachments via the configured
adapter before redeeming them through `GET /shares/{token}`. `GET /routes/hello/schema` returns auto-form metadata for client
builders.
