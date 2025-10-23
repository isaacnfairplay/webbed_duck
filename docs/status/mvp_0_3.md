# MVP 0.3 Status Report

## Highlights

- Overlay store wired into the FastAPI application with REST endpoints for listing and creating overrides. Author hashes and user identifiers are persisted alongside each override event.
- CSV append workflows, schema introspection, and auto-form metadata surfaced via `/routes/{id}/append` and `/routes/{id}/schema`.
- Local execution helpers (`webbed_duck.core.local.run_route`) and the `run-incremental` CLI command support cursor-driven workloads while recording checkpoints under `runtime/checkpoints.json`.
- Configuration expanded with auth adapter selection, sample route metadata refreshed for overrides and append targets, and documentation updated to describe the new surface area.

## Storage Layout Additions

- `runtime/overrides.json` – JSON-backed overlay store with per-route override entries.
- `runtime/appends/` – CSV append destination created on demand by append-enabled routes.
- `runtime/checkpoints.json` – Incremental runner checkpoint log keyed by route and cursor parameter.

## Testing Summary

- FastAPI integration tests cover override creation, schema discovery, and CSV append flows.
- Local execution and incremental runner unit tests validate Arrow output and checkpoint persistence.
- Existing compiler and server tests remain green under the upgraded toolchain.

