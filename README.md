# webbed_duck

`webbed_duck` turns Markdown + SQL route files into HTTP endpoints powered by DuckDB.

This MVP (v0.3) extends the core compiler and server with annotation-ready viewers and workflow helpers:

* A Markdown compiler that translates `*.sql.md` files into Python route manifests and preserves per-route metadata for cards,
  feeds, charts, overrides, and append targets.
* A FastAPI-based server that executes DuckDB queries per-request, applies per-cell overrides from the overlay store, and
  returns JSON payloads derived from Arrow tables, HTML tables (`html_t`), card grids (`html_c`), feed views, and Arrow stream
  slices for virtualized viewers.
* New endpoints for `/routes/{id}/schema`, `/routes/{id}/overrides`, `/routes/{id}/append`, and `/shares` to expose form
  metadata, manage overrides, persist CSV append operations, and generate shareable artifacts.
* Popularity analytics, folder indexes, and a pluggable auth adapter resolved via configuration. Pseudo-auth tokens and share
  secrets are hashed on disk, with optional binding to client IP prefixes or user agents for additional guardrails.
* Command-line tooling for compiling routes, running the development server, and iterating cursor-driven workloads via
  `run-incremental`, which persists progress in `runtime/checkpoints.duckdb` for resumable execution.

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

Visit `http://127.0.0.1:8000/hello?name=DuckDB` to exercise the sample route. Append `&format=html_c` or `&format=feed` to
see the HTML viewers, or `&format=arrow&limit=25` for Arrow RPC slices. Use `POST /routes/hello/overrides` to annotate rows,
`POST /routes/hello/append` to persist CSV records, and `GET /routes/hello/schema` to generate auto-form metadata.

To create shareable artifacts, call `POST /shares` with a `route_id`, desired `format`, and optional attachment preferences. The
server records share metadata in SQLite, renders requested attachments (CSV, Parquet, HTML), and can watermark inline HTML when
configured. Download tokens inherit the same hashing and optional client-binding rules as pseudo-auth sessions.

## Encrypted ZIP attachments

Shares can optionally bundle CSV, Parquet, or HTML artifacts into a ZIP archive. If a share request specifies a
`zip_passphrase`, webbed_duck encrypts the archive with AES via the optional [`pyzipper`](https://pypi.org/project/pyzipper/)
dependency. Install it with:

```bash
pip install pyzipper
```

When `pyzipper` is not installed the server still produces plain ZIP archives and reports `"zip_encrypted": false` in the
share metadata. Passphrase requests are rejected in this scenario so teams that require encryption can surface the missing
dependency quickly.
