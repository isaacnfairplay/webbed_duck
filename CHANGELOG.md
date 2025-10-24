# Changelog

## Unreleased

- Fixed the wheel build configuration so the published package exposes the
  `webbed_duck` module (rather than leaking `core`/`server` at the top level),
  and added a packaging test that verifies the generated wheel structure.

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
- Replaced the README with product-grade docs covering the `.sql.md` contract,
  runtime formats, and the standalone server workflow.
- Delivered a config-driven auto-compiling `webbed-duck serve` command with
  optional watch mode and FastAPI route hot-reload support for `.sql.md`
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
- Included sample route (`routes_src/hello.sql.md`) and compiled manifest.
- Added pytest coverage for compiler and server basics.
