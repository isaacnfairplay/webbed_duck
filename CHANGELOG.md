# Changelog

## Unreleased

- Documented the layered UI architecture, route `[ui]` asset contract, and new progressive-enhancement plugins in the README, added a UI migration guide, and updated README coverage tests for the Chart.js embed snippet.
- Added regression tests to cover string-based `[ui]` metadata and asset fallbacks to ensure layout rendering ignores unknown styles or scripts gracefully.

## 0.4.6 - 2025-03-10

- Default invariant-backed parameters to dynamic HTML select options powered by the
  `"...unique_values..."` sentinel and document the workflow in the README and docs.
- Hardened the Chart.js vendor bootstrap with deterministic unit tests, a
  simplified result container, and a shared setup helper that drives the
  FastAPI state plus README guidance for air-gapped deployments.
- Bundled the Chart.js 4.4.3 runtime under `webbed_duck.static.chartjs` so the
  package can serve the asset without downloading it at startup, and added a
  regression test that verifies the script ships in the wheel.
- Added a `chart_js` response format that converts route `[[charts]]` metadata into
  Chart.js canvases, including an embeddable `?embed=1` snippet, vendored
  runtime assets served from `/vendor/chart.umd.min.js`, and configurable
  script overrides via `[chart_js]` metadata or postprocess settings.
- Simplified the `/routes` index by extracting folder aggregation into a helper,
  paving the way for reuse in analytics surfaces and clarifying how metrics roll
  up across nested folders.
- Clarified the FastAPI/Uvicorn dependency guidance in the README and README
  coverage test so packaging metadata and documentation stay aligned when
  altering optional extras.
- Extracted email adapter loading into a dedicated module with callable
  validation, unit tests, and README guidance so share workflows fail fast when
  misconfigured.
- Hardened CLI ergonomics by extracting a reusable source fingerprint helper and
  adding unit tests around CLI parameter parsing, date validation, and watcher
  change detection.
- Documented CLI `perf` dependencies and the file-fingerprint watch strategy in
  the README so contributors understand the prerequisites for latency testing
  and hot reloads.
- Hardened executor and append coverage: added failure-path tests for parameter
  coercion, parquet dependencies with empty results, append misconfiguration
  flows, and MetaStore schema upgrades; refactored DuckDB execution helpers to
  share connection logic and removed the unused `render_cards_html` wrapper.
- Documented watch interval performance considerations plus FastAPI testing
  prerequisites in the README so contributors understand skipped integration
  cases.
- Added compile-time warnings for unknown TOML frontmatter keys so route authors
  catch typos before deployment.
- Implemented paged Parquet caching with configurable TTLs and route-defined
  `rows_per_page` limits, reusing on-disk slices across HTTP requests and the
  local runner.
- Introduced a dependency-aware route executor that honors `[[uses]]` metadata,
  supporting both relation and parquet_path modes while respecting per-route
  `cache_mode` controls.
- Extended configuration with a `[cache]` section and refreshed the README with
  a request-lifecycle mermaid diagram covering the new caching flow.
- Added transformation-invariant cache filters so routes can reuse superset
  pages and combine existing shards for filtered requests without hitting
  DuckDB, including multi-value combinations defined via `separator` settings.
- Documented invariant filter frontmatter and expanded the cache test suite to
  cover superset reuse and shard combination scenarios.
- Refreshed the README to document the TOML + SQL route layout, declarative
  dependencies, and safe parameter binding patterns (including multi-value
  `IN` filters and named bindings).
- Added NYC taxi-inspired performance regression tests that exercise
  cache-backed execution across increasing data volumes and verify cache hits
  accelerate repeat requests.
- Required routes that opt into caching to declare `cache.order_by` columns and
  taught the cache store to re-sort combined superset/shard hits before paging,
  eliminating inconsistent ordering when invariant filters are reused.

## 0.4.3 - 2025-03-08

- Fixed the wheel build configuration so the published package exposes the
  `webbed_duck` module (rather than leaking `core`/`server` at the top level),
  and added a packaging test that verifies the generated wheel structure.
- Restored HTML filter controls for parameters declared with `ui_control`
  metadata so table (`html_t`) and card (`html_c`) views surface interactive
  inputs based on each route's `show_params` list.
- Documented the HTML filter workflow, including how `show_params` influences
  auto-generated forms and how the embedded RPC metadata can be used to page
  through Arrow slices.
- Updated `html_t` and `html_c` renderers to emit Arrow RPC metadata (`Link`
  headers, `wd-rpc-config` script, and download links) while mirroring the
  pagination headers from the RPC endpoint so downstream clients can request
  additional slices with explicit offsets and limits.
- Added regression tests that assert the generated HTML includes the filter
  controls, hidden pagination inputs, RPC headers, and the embedded Arrow RPC
  configuration block for both table and card views.

## 0.4.1 - 2025-03-06

- Added a Windows-only `tzdata` dependency so packaged builds include a
  timezone database on platforms lacking system zoneinfo files.

## 0.4.0 - 2025-03-05

- Added extensive plugin registry tests that verify custom image getters,
  fallback behaviour, and chart renderer edge cases.
- Documented the plugin architecture with a standalone demo script and guide
  under `docs/demos/`.
- Documented the optional `pyzipper` dependency for encrypted share archives
  and exposed `zip_encrypted` metadata so passphrase requests fail fast when
  encryption is unavailable.
- Updated project documentation (README, AGENTS guide, status report) to reflect
  DuckDB-backed incremental checkpoints, share workflows, and security
  guardrails for pseudo-auth sessions and share tokens.
- Replaced the README with product-grade docs covering the TOML/SQL sidecar contract,
  runtime formats, and the standalone server workflow.
- Delivered a config-driven auto-compiling `webbed-duck serve` command with
  optional watch mode and FastAPI route hot-reload support for sidecar
  contract changes.

## MVP 0.3

- Added an overlay store with REST endpoints for listing and creating per-cell overrides, including author hashes and user identifiers resolved through the auth adapter.
- Introduced CSV append workflows and auto-form metadata via new `/routes/{id}/schema` and `/routes/{id}/append` endpoints.
- Added a local route runner (`webbed_duck.core.local.run_route`) and an incremental CLI command for iterating cursor-driven workloads while persisting checkpoints.
- Upgraded configuration with auth adapter selection, refreshed the sample route metadata, and documented the new capabilities in the README.

## MVP 0.2

- Upgraded the FastAPI application to deliver HTML tables, card grids, feed views, and Arrow RPC slices with error-taxonomy
  aware responses.
- Added chart and asset plugin registries, popularity analytics, and a `/routes` index for folder-aware navigation.
- Persisted per-route metadata from compiled Markdown into runtime manifests and refreshed the sample route to surface cards,
  feeds, and charts.
- Removed the temporary repository status document and legacy publish workflow in favor of the consolidated release process.

## MVP 0.1

- Added project packaging (`pyproject.toml`) and configuration loader.
- Implemented Markdown-to-Python route compiler with parameter handling.
- Created FastAPI application factory that executes DuckDB queries per request.
- Added CLI commands for compiling routes and running the development server.
- Included sample route (`routes_src/hello.toml` + `hello.sql`) and compiled manifest.
- Added pytest coverage for compiler and server basics.
