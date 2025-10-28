# Branch-level Changelog

## Local reference coverage + CLI guardrails (work branch)

- Factor `/local/resolve` payload parsing into a typed helper reused by the endpoint so validation and formatting stay aligned with share flows.
- Add FastAPI tests that exercise happy-path, coercion, and error handling for local references, plus a CLI test proving the watch interval clamp stays at the documented 0.2s minimum.
- Document the `/local/resolve` workflow for internal automation so developers avoid reimplementing share parameter coercion.

## Cache pagination and analytics guardrails (work branch)

- Document the CLI watch interval floor and cache enforcement toggle so route authors understand when limits are honoured.
- Add FastAPI regression tests covering `[cache.enforce_page_size = false]` and analytics-disabled runs to keep behaviour from regressing.
- Extracted a helper inside `server.app` that records analytics only when the feature is enabled, trimming direct state pokes and easing future refactors.

## Incremental runner resilience (work branch)

- Refactored `core.incremental.run_incremental` to accept a pluggable runner, reuse
  a shared date-range helper, and skip already checkpointed days without manual
  loops.
- Added regression tests that prove checkpoint reuse, failure handling, and the
  absence of partial checkpoint writes when a run raises an error.
- Documented the helper in the README, including guidance on optional FastAPI
  dependencies so test environments exercise the HTTP stack before release.

## CLI coverage hardening (work branch)

- Add direct unit coverage for `webbed-duck compile`, `run-incremental`, and `serve`
  entry points by monkeypatching compiler, executor, and uvicorn dependencies.
- Remove the unused `EmailSender` import from `server.app` to keep runtime imports tidy.
- Call out the optional FastAPI/Uvicorn extras next to the CLI docs so developers
  know which packages are required for end-to-end HTTP testing.

## Email adapter validation (work branch)

- Extracted email adapter loading into `webbed_duck.server.email.load_email_sender`
  so FastAPI setup and tests share validation logic.
- Added unit tests for colon-separated and dotted adapter paths plus the
  non-callable guard to catch misconfiguration before shares attempt delivery.
- Documented the callable requirement for `config.email.adapter` in the README
  to steer contributors away from referencing module-level constants.

## Auth adapter robustness (work branch)

- Harden external auth adapter loading by inspecting adapter factory signatures
  before invocation so genuine `TypeError`s bubble up instead of being masked by
  retry logic.
- Document the external adapter contract in the README and add regression tests
  covering config-aware factories and error propagation.

## Plugin registry reset + local runner guardrails (work branch)

- Expose `reset_image_getters` / `reset_chart_renderers` helpers so tests and
  extensions can temporarily swap registries without poking private module
  globals.
- Expand plugin tests to cover registry resets and keep coverage focused on the
  fallback image getter.
- Add local-runner regression cases for unknown routes and invalid formats to
  lock down error semantics used by docs and CLI helpers.
- Refresh README guidance on canonical TOML/SQL route sources, filesystem watch
  caveats, and the deprecation status of HTML comment directives.

## Route authoring guidance refresh (work branch)

- Rewrite the README around the new TOML + SQL route layout, covering
  dependency metadata, execution modes, and the compiler's legacy `.sql.md`
  import path.
- Add a detailed "How parameters work" section documenting safe named binding,
  multi-value filters, and cache-aware distinctions between persistent and
  ephemeral parameters.
- Update changelog entries to point readers at the refreshed docs and parameter
  guidance.

## Route composition runtime (work branch)

- Add a dependency-aware route executor that resolves `[[uses]]` entries for
  both relation and parquet_path modes while sharing cache/coercion logic with
  HTTP requests and the local runner.
- Materialize parquet artifacts on demand so downstream routes can reference
  cached pages without re-running upstream queries.
- Update the FastAPI app and local runner to use the new executor, enabling
  declarative route composition without manual glue code.

## webbed_duck packaging hardening (work branch)

- Fix setuptools configuration so `pip install webbed-duck` installs the actual
  `webbed_duck` package hierarchy instead of leaking `core/`, `server/`, and
  `plugins/` modules at the root of site-packages.
- Add an optional `[test]` extra that pulls in `build` and a regression test
  that constructs a wheel and asserts the package layout is correct.
- Regenerate the sample `hello` route so its compiled artifact reflects the
  current compiler metadata (formats, postprocessors, directives).

## UI filters + Arrow RPC plumbing (work branch)

- Document how `[html_t]` / `[html_c]` `show_params` metadata drives parameter
  forms and demonstrate the workflow in the README.
- Update the HTML renderers to emit `wd-rpc-config` JSON, pagination summaries,
  and Arrow RPC download links while mirroring the RPC headers on responses.
- Expand the regression suite with tests that assert filter controls, hidden
  pagination inputs, and RPC metadata render for both table and card formats.

## Performance regression coverage (work branch)

- Generate NYC taxi-style Parquet fixtures on the fly and compile TOML/SQL
  routes against them to stress the executor with small, medium, and large
  workloads.
- Assert that first-run timings grow with the dataset size while parquet-backed
  cache hits respond faster than the initial materialisation.
- Verify that cache materialisation leaves behind parquet page artifacts so
  downstream parquet_path consumers can reuse them.

## Parameter coercion regression (work branch)

- Add executor-level tests that coerce every supported parameter type
  (string, integer, float, and boolean) while exercising repeated placeholders
  inside nested queries.
- Cover multi-value inputs by binding repeated parameters as Python lists so
  the executor preserves sequence values for `IN $param` filters.
