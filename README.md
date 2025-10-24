# webbed_duck

`webbed_duck` is an opinionated, securable intranet platform that compiles Markdown + SQL route files into auditable HTTP APIs and HTML experiences backed by DuckDB and Apache Arrow. The project ships a deterministic compiler, a FastAPI runtime, and a library of pluggable adapters so teams can publish dashboards, self-serve data apps, and shareable extracts without bespoke backend glue.

This README is the canonical onboarding document. It explains what the project does, how the pieces fit together, and how to operate it confidently in development and production-style environments.

## Table of contents

1. [Feature overview](#feature-overview)
2. [Architecture in brief](#architecture-in-brief)
3. [Repository structure](#repository-structure)
4. [Prerequisites](#prerequisites)
5. [Installation](#installation)
6. [Configuration](#configuration)
7. [Authoring routes](#authoring-routes)
8. [Build & serve workflow](#build--serve-workflow)
9. [Runtime capabilities](#runtime-capabilities)
10. [Storage layout](#storage-layout)
11. [Security & hardening](#security--hardening)
12. [Testing & quality](#testing--quality)
13. [Troubleshooting](#troubleshooting)
14. [Project status & roadmap](#project-status--roadmap)
15. [Contributing](#contributing)
16. [Additional resources](#additional-resources)

## Feature overview

* **Markdown + SQL compiler** – Author `*.sql.md` files that embed SQL, parameters, preprocessors, postprocessors, charts, and append destinations. A deterministic compiler turns each file into an importable Python module with typed metadata and route manifests.
* **Per-request DuckDB execution** – Every HTTP request opens a fresh DuckDB connection, applies trusted preprocess hooks, executes SQL, and returns Apache Arrow-backed results that can be rendered as JSON, HTML (`html_t` tables or `html_c` card grids), feeds, or Arrow streaming slices for infinite-scroll UIs.
* **Overlay-aware viewers** – Opt-in endpoints expose inline annotations, CSV-backed append flows, and generated schemas for auto-forms. Overlay metadata lives beside compiled routes so teams can audit changes.
* **Share engine** – `POST /shares` materializes HTML, CSV, or Parquet artifacts, optionally bundles them into encrypted ZIP archives, and records access analytics.
* **Configurable auth adapters** – Choose pseudo-auth tokens, basic auth, or plug in a custom adapter. All tokens and share secrets are hashed on disk and can be bound to user agents or IP prefixes.
* **Incremental execution** – Long-running extract routes can persist resume checkpoints in DuckDB and continue where the last cursor stopped.
* **Extensible plugins** – Register custom preprocessors, postprocessors, chart renderers, and asset getters to integrate with internal systems without forking the runtime.

See the [Quickstart workspace setup](#quickstart-workspace-setup) section for a self-contained starter route. Additional examples live under [`docs/`](docs/) and [`examples/`](examples/) if you cloned the repository for reference.

## Architecture in brief

1. **Authoring** – Developers write Markdown+SQL route files that describe inputs, SQL statements, and output formats.
2. **Compilation** – `webbed_duck.cli compile` parses each route into a Python manifest stored under `routes_build/`.
3. **Serving** – The FastAPI runtime imports the compiled modules, validates requests, executes DuckDB queries, and emits Arrow-backed responses.
4. **Extensions** – Optional preprocessors, chart renderers, share adapters, and overlay storage providers integrate through registries in the `webbed_duck` package.

For an exhaustive architectural deep-dive—including flow diagrams, invariants, and adapter lifecycle details—consult [`AGENTS.md`](AGENTS.md).

## Repository structure

```
webbed_duck/
├── CHANGELOG.md          # Release history
├── README.md             # You are here
├── config.toml           # Example runtime configuration
├── docs/                 # Extended design and API documentation
├── examples/             # Helper scripts (e.g., SMTP emailer)
├── routes_src/           # Authoring source (.sql.md routes)
├── routes_build/         # Compiled Python manifests (generated)
├── tests/                # Pytest suite exercising compiler & runtime
└── webbed_duck/          # Python package: compiler, runtime, plugins
```

## Prerequisites

* Python 3.9 or newer
* DuckDB (installed automatically via Python package dependency)
* Access to an intranet or trusted environment for serving HTTP traffic
* Optional: `pyzipper` for encrypted ZIP share attachments

Use a virtual environment (`venv`, `pipenv`, or `conda`) to isolate dependencies.

## Installation

Install the published package from PyPI (no repository clone required):

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install webbed-duck
```

Optional extras:

```bash
pip install pyzipper            # Enables encrypted ZIP shares and ZIP encryption policies
pip install "duckdb[excel]"     # Adds Excel import support for DuckDB
```

After upgrades, rerun `pip install --upgrade webbed-duck` inside the virtual environment to pick up the latest release.

## Configuration

`webbed_duck` reads a TOML configuration file at startup. The sample `config.toml` ships with sensible defaults:

```toml
[server]
storage_root = "./storage"
host = "127.0.0.1"
port = 8000
theme = "system"           # system, light, or dark

[transport]
mode = "insecure_http"     # or "proxy_tls" behind a trusted proxy
trusted_proxy_nets = ["127.0.0.1/32", "10.0.0.0/8"]

[auth]
mode = "pseudo"            # pseudo, basic, or custom module path
allowed_domains = ["company.local"]
session_ttl_minutes = 45

[share]
max_total_size_mb = 15
zip_attachments = true
zip_passphrase_required = false

[analytics]
enabled = true
weight_interactions = 3

[feature_flags]
annotations_enabled = true
comments_enabled = true
tasks_enabled = true
overrides_enabled = true

[assets]
default_image_getter = "static_fallback_getter"
```

Key principles:

* **`storage_root`** anchors runtime state (compiled routes, cache, runtime metadata, static assets). Use an absolute path in production.
* **Auth adapters** are referenced by name (`pseudo`, `basic`) or via dotted Python paths for custom implementations.
* **Transport mode** determines whether the runtime trusts upstream headers. Use `proxy_tls` when deploying behind a TLS-terminating proxy.
* **Feature flags** toggle overlay components, annotations, and tasks per route.

After editing `config.toml`, re-run the compiler so configuration-sensitive metadata is baked into the manifests.

## Quickstart workspace setup

Once the package is installed, create a working directory to hold your configuration, source routes, and compiled artifacts:

```bash
mkdir -p storage routes_src routes_build
cat > config.toml <<'EOF'
[server]
storage_root = "./storage"

[transport]
mode = "insecure_http"

[auth]
mode = "pseudo"
allowed_domains = ["example.com"]
EOF
```

Add a starter route at `routes_src/hello.sql.md`:

```markdown
@route id="hello"
@params name:text="DuckDB"
@sql
select 'Hello, ' || {{ name }} || '!' as greeting
```

This minimal setup is enough to compile, serve, and experiment with the runtime. Expand the configuration and routes as needed for your intranet deployment.

## Authoring routes

Routes live in `routes_src/` as Markdown files with embedded SQL blocks. Core directives include:

* `@route` – Declares the route identifier and optional folder grouping.
* `@params` – Defines typed input parameters (strings, ints, floats, dates, enums) with validation rules and defaults.
* `@preprocess` – Points to trusted Python callables for parameter enrichment or guardrails before SQL execution.
* `@sql` – Contains one or more DuckDB statements. Use `{{param}}` placeholders for bound parameters.
* `@postprocess` – Chooses output renderers (`html_t`, `html_c`, `feed`, `arrow`, etc.).
* `@charts` – Registers chart specifications consumed by UI plugins.
* `@append` – Enables CSV-backed data entry flows.
* `@assets` – References static assets (images, CSS) resolved through registered getters.

Authoring tips:

* Favor set-based SQL over Python loops—DuckDB is the primary compute engine.
* Keep preprocessors deterministic and side-effect free.
* Use folders to group related routes and enable aggregated analytics.

Run `webbed-duck compile` (or `python -m webbed_duck.cli compile`) after editing routes to regenerate manifests.

## Build & serve workflow

1. **Compile** routes from Markdown into Python modules:

   ```bash
   webbed-duck compile --source routes_src --build routes_build
   ```

2. **Serve** the compiled routes with FastAPI/Uvicorn:

   ```bash
   webbed-duck serve --build routes_build --config config.toml
   ```

3. **Visit** `http://127.0.0.1:8000/hello?name=DuckDB` to explore the sample route. Append `format=html_c`, `format=feed`, or `format=arrow&limit=25` to test alternate viewers.

4. **Interact** with overlays:
   * `POST /routes/{route_id}/overrides` – Create annotations or overrides.
   * `POST /routes/{route_id}/append` – Append CSV rows respecting schema validation.
   * `GET /routes/{route_id}/schema` – Retrieve auto-generated form metadata.

5. **Share** results:

   ```bash
   curl -X POST http://127.0.0.1:8000/shares \
     -H 'Content-Type: application/json' \
     -d '{"route_id": "hello", "format": "html_t", "zip_passphrase": null}'
   ```

   The runtime stores share metadata in `runtime/meta.sqlite3`, materializes requested artifacts, and enforces optional ZIP encryption policies.

6. **Run incremental workloads** for cursor-based extracts:

   ```bash
   python -m webbed_duck.cli run-incremental \
     --route-id hello_world \
     --build routes_build \
     --config config.toml \
     --cursor-column created_at
   ```

   Progress persists in `runtime/checkpoints.duckdb` so reruns resume automatically.

## Runtime capabilities

* **Request lifecycle** – Each request validates parameters, executes preprocessors, runs DuckDB SQL, optionally applies postprocessors, and returns results encoded as Arrow, JSON, HTML, feeds, or downloadable artifacts.
* **Analytics** – Route hits, row counts, latency, and interaction weights accumulate in the runtime store to power folder-level popularity summaries.
* **Local route chaining** – Use the internal `local:` protocol to call other routes without HTTP roundtrips.
* **Static assets** – Register image getters (see `plugins/assets.py`) to resolve per-route images or UI assets.
* **Email integration** – Example emailer in `examples/emailer.py` demonstrates how to deliver share links via SMTP.

## Storage layout

All runtime paths derive from the configured `storage_root`:

```
storage_root/
├── routes_build/         # Compiled manifests imported by the server
├── cache/                # Materialized CSV/Parquet/HTML artifacts
├── schemas/              # Arrow schemas (JSON) per route
├── static/               # Packaged CSS/JS/images referenced by UI
└── runtime/
    ├── meta.sqlite3      # Sessions, shares, analytics
    ├── checkpoints.duckdb# Incremental runner checkpoints
    └── auth.duckdb       # Pseudo/basic auth adapter backing store
```

Ensure the service user has read/write access to `storage_root` when deploying.

## Security & hardening

* **Securable by design** – Intended for trusted intranets with clear paths to add TLS, authentication, and logging through modular adapters.
* **Connection management** – One DuckDB connection per request; no shared cursors.
* **Secrets hygiene** – Tokens and share secrets are hashed; no plaintext storage.
* **Path safety** – All file access is rooted under `storage_root` to prevent traversal attacks.
* **Proxy deployment** – Terminate TLS at a trusted proxy (e.g., Nginx, Traefik) and use `transport.mode = "proxy_tls"` so `webbed_duck` honors `X-Forwarded-*` headers safely.
* **External auth** – Implement custom auth adapters or integrate session validation middleware to hook into SSO providers when required.

## Testing & quality

Run the pytest suite before submitting changes:

```bash
pytest
```

The suite exercises compiler parsing, preprocess execution, share workflows, overlay storage, analytics aggregation, and error taxonomy mapping. Add regression tests when extending compiler directives, runtime adapters, or plugins.

Linting can be layered on with tools such as `ruff` or `black` if your team prefers additional static analysis (not enforced by default).

## Troubleshooting

* **Missing compiled routes** – Ensure `routes_build/` exists and rerun `webbed_duck.cli compile` after editing source files or configuration.
* **ZIP encryption disabled** – Install `pyzipper` and confirm `share.zip_passphrase_required = false` unless enforcing passphrases.
* **Authentication failures** – Verify adapter configuration, session TTLs, and whether `allowed_domains` matches the pseudo-auth email domain.
* **Proxy misconfiguration** – When running behind a reverse proxy, configure `trusted_proxy_nets` to match the proxy subnet so upstream headers are accepted.
* **DuckDB locking errors** – Check for stale processes holding open connections; every request should open and close its own connection.

## Project status & roadmap

* Current release: 0.3 (see `CHANGELOG.md` for details).
* Major focuses: compiler determinism, share/overlay workflows, incremental execution, analytics, and plugin ergonomics.
* Upcoming ideas: richer chart plugins, expanded auth adapters, and improved telemetry visualizations.

Refer to the maintainer logs inside [`AGENTS.md`](AGENTS.md) for ongoing progress trackers and architectural context.

## Contributing

1. Fork the repository and create a topic branch.
2. Install dependencies in a virtual environment.
3. Run `pytest` (and any project-specific linters your team adopts) before opening a pull request.
4. Document new behavior in `README.md`, `docs/`, or inline docstrings as appropriate.
5. Follow the invariants listed in [`AGENTS.md`](AGENTS.md)—especially around DuckDB connections, trusted preprocessors, and storage isolation.

Bug reports and feature requests are welcome via issues. Please include reproduction steps, relevant configuration snippets, and any failing route manifests to streamline triage.

## Additional resources

* [`AGENTS.md`](AGENTS.md) – Comprehensive architecture and maintainer guide.
* [`docs/`](docs/) – Extended documentation, diagrams, and design notes.
* [`examples/emailer.py`](examples/emailer.py) – Minimal SMTP emailer used in tests and demos.
* [`CHANGELOG.md`](CHANGELOG.md) – Release notes and historical context.

Happy routing!
