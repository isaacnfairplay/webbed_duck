# Changelog

## Unreleased

- Added a pseudo-authentication adapter with SQLite-backed session storage and
  login/logout endpoints plus `/auth/me` for session introspection.
- Added extensive plugin registry tests that verify custom image getters,
  fallback behaviour, and chart renderer edge cases.
- Documented the plugin architecture with a standalone demo script and guide
  under `docs/demos/`.
- Corrected the plugin registry demo module docstring and ensured the new test
  suite isolates registry state with pytest fixtures.
- Implemented hashed share tokens with TTL/binding controls, new `/shares`
  endpoints, configuration knobs, and regression tests for the SQLite store
  plus the FastAPI flow.
- Defaulted the auth configuration to pseudo sessions so login and share
  endpoints come online without additional settings, and deferred share token
  binding to first redemption while normalizing hostname-based clients for IP
  safeguards.

- Added CSV and Parquet response formats alongside CSV download tests for the compiler integration suite.
- Enabled share emails with configurable adapters, zipped CSV/Parquet attachments, and guardrails for attachment sizing.
- Introduced proxy header authentication and external adapter loading so deployments can bridge to upstream identity providers.
- Shipped a perf harness script (`examples/perf_harness.py`) and documentation for benchmarking compiled routes without HTTP overhead.

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
- Included sample route (`routes_src/hello.sql.md`) and compiled manifest.
- Added pytest coverage for compiler and server basics.
