# MVP 0.4 Status Report

## Highlights

- `webbed-duck serve` now auto-compiles contracts from the configured `server.source_dir` and hot-reloads FastAPI routes when watch mode is enabled.
- Config defaults cover the full quick start: source/build directories, auto-compile toggles, and watch intervals are all part of `config.toml`.
- Dynamic route registration keeps `/routes/{id}` helpers, share workflows, and local route chaining in sync with newly compiled contracts.

## Developer Experience

- CLI gains `--no-auto-compile`, `--watch`, and `--watch-interval` flags plus a built-in file watcher for TOML/SQL sidecar contracts.
- README, quick start steps, and configuration examples document the zero-boilerplate workflow and live reload behaviour.

## Testing Summary

- Added regression coverage for dynamic route reloads to ensure new compilations refresh FastAPI endpoints without restarting the app.
- Existing compiler, server, share, and plugin tests continue to validate overlays, append flows, email delivery, and Arrow exports.
