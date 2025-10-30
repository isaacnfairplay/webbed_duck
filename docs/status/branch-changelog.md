# Branch-level Changelog

## IPv6 binding case hardening (work branch)

- Add share and session regression tests that create bindings with uppercase
  IPv6 hosts and assert the lowercase variants continue to resolve, preventing
  case-only mismatches when proxies normalise address strings differently.
- Normalise IPv6 literals to lowercase in the share and session IP prefix
  helpers so persisted bindings are case-insensitive without weakening the
  prefix truncation behaviour.
- Document the case-normalisation behaviour in the README alongside the
  existing binding overview so operators understand the runtime guarantees.

## Cache invariant large-string handling (work branch)

- Guard case-insensitive invariant filters against Arrow `large_string` columns
  so cache reuse works for wide text datasets emitted by DuckDB.
- Add a focused unit test that exercises `_apply_invariant_filters` with
  mixed-case `large_string` values to catch regressions without requiring the
  HTTP stack.
- Document the fix in `CHANGELOG.md` so downstream consumers understand why the
  cache helper changed.

## UI asset ordering guardrails (work branch)

- Preserve canonical ordering for built-in styles/scripts while respecting
  route-defined placement of custom assets so bespoke themes can control when
  their files load.
- Extend the UI renderer tests to cover CSV metadata parsing and explicit
  ordering for custom styles/scripts, exercising the new deterministic helper.
- Document the ordering semantics in the README and UI migration guide so route
  authors know how to interleave custom assets without duplicating defaults.
- Add a regression test around `LocalRouteRunner` error translation to ensure
  execution failures continue to surface as `ValueError` instances for CLI and
  library consumers.

## Version metadata alignment (work branch)

- Restore the static `webbed_duck.__version__` constant and ensure it reflects
  the current release number.
- Update the version bump workflow to rewrite both `pyproject.toml` and
  `webbed_duck/__init__.py` so automated releases keep the runtime version in
  lockstep with packaging metadata.
- Keep the regression test that parses `pyproject.toml` to guard the sync in the
  future.

## Version bump workflow YAML fix (work branch)

- Indented the inline Python scripts inside `.github/workflows/version-bump.yml`
  so GitHub Actions parses the job correctly and runs the merge-time version
  bump instead of failing before any steps execute.
- Documented the workflow repair in `CHANGELOG.md` to highlight why the release
  automation resumed working after the merge that introduced the job.

## Watch iteration helper and feature flag parsing (work branch)

- Extracted a reusable `_watch_iteration` helper for the CLI file watcher and
  covered both change and no-change paths with unit tests so hot reload failures
  surface immediately.
- Added parsing for the documented `[feature_flags]` configuration table and a
  regression test confirming the toggles flow into `Config.feature_flags`.
- Documented the refactor in the project changelog so future contributors notice
  the new helper when extending watch behaviour.

## Chart dataset temporal coverage (work branch)

- Add regression coverage that feeds datetime and boolean series through
  `build_chartjs_configs`, ensuring conversions emit Unix timestamps and numeric
  flags so any missing imports or coercion bugs surface immediately.
- Align the FastAPI app version with the package `__version__` (now `0.4.7`) so
  diagnostics and UI asset cache-busting share the same semantic version.
- Clarify the UI migration guide to note the layered renderer shipped during the
  0.4.7 cycle on the path to 0.5 instead of implying it is future-only.

## Plugin registry hygiene (work branch)

- Tighten `webbed_duck.plugins.assets.get_image_getter` so registry lookups raise
  when both the requested getter and the `static_fallback` entry are missing.
- Extend `tests/test_plugins.py` to cover empty registries and the new
  `LookupError` signalling.
- Document the requirement to re-register a fallback getter in
  `docs/demos/plugin_registry.md`, keeping downstream plugin tests aligned.

## Pseudo auth HTTP coverage (work branch)

- Add FastAPI regression tests that exercise the `/auth/pseudo/session` lifecycle,
  ensuring cookies, payload validation, and delete flows match the documented
  behaviour.
- Introduce a shared JSON payload helper in the server app so pseudo auth,
  overrides, append, and share endpoints surface consistent error messages.
- Extend the Chart.js vendor route coverage to assert the vendored asset serves a
  200 response and returns a 404 when the script is missing.
- Document that pseudo auth and share flows require FastAPI/Uvicorn and remind
  teams to compile routes before running the `perf` harness.

## Multi-select dropdown refinement (work branch)

- Replace the basic `<select multiple>` widgets with a compact dropdown shell
  that keeps the filter controls feeling like standard comboboxes instead of
  sprawling checkbox walls.
- Layer in a case-insensitive search box, persistent "add to selection" hint,
  and a clear button so analysts can quickly drill into long value lists and
  reset a column without navigating away.
- Ship responsive styles plus lightweight bootstrap JavaScript that syncs the
  visible checkboxes with the hidden form control, enabling smooth desktop and
  mobile filtering without regressing the server-rendered forms.

## Multi-select UI defaults (work branch)

- Default every select control to allow multi-value submissions while keeping
  dynamic option lists compatible with invariant cache metadata and live table
  fallbacks.
- Normalize current parameter values so multiple selections remain selected and
  stay visible even when filtered out of the rendered table.
- Extend postprocess renderer regression coverage to exercise multi-select
  behaviour across invariant-driven, table-driven, and card layouts.

## Invariant select filtering (work branch)

- Filter invariant-backed select dropdowns against the currently rendered
  result table so downstream filters only offer values that remain valid after
  other controls are applied.
- Preserve a user's existing selection even when it no longer appears in the
  filtered table, preventing the UI from unexpectedly clearing chosen values.
- Extend the postprocess renderer coverage to lock in the filtered invariant
  behaviour alongside the existing table fallback scenarios.

## Default dynamic select options (work branch)

- Make HTML select controls default to dynamically generated unique values when a
  parameter declares `ui_control = "select"` without an explicit `options`
  list, so authors get filter-aware dropdowns by default.
- Reuse cached invariant metadata when present and fall back to the current
  result table when caches are cold, ensuring the option list keeps pace with
  the active filters.
- Extend the postprocess renderer tests to cover the new default behaviour and
  the cache-backed path so both HTML tables and cards stay covered by
  regression tests.

## Unique select fallback (work branch)

- Teach the HTML parameter renderer to fall back to the current result table
  when `options = "...unique_values..."` is requested but cache metadata lacks
  an invariant index, so dropdowns still populate during first-run or
  passthrough executions.
- Add renderer-level regression tests that cover both invariant-index driven
  options and the new table fallback, ensuring static choices continue to merge
  cleanly with dynamic entries.

## HTML invariant filter enforcement (work branch)

- Fix cache metadata to record the actual invariant tokens present in cached pages
  so post-cache filtering triggers whenever requests provide a subset of cached
  values.
- Re-read newly populated cache entries through the invariant-aware reader path
  to serve filtered tables on the first request instead of only after warmup.
- Add a FastAPI regression test covering HTML table rendering with invariant
  filters and drop the temporary invariant filter bug report doc.

## Dynamic invariant select options (work branch)

- Allow parameter `options = "...unique_values..."` to populate `<select>`
  controls with unique values derived from cached invariant metadata and the
  current result set when other invariants are active.
- Default invariant-backed parameters without explicit `options` to the same
  dynamic list so HTML forms stay in sync with cached filter values.
- Extend the postprocess helpers to reuse parsed invariant settings, decode
  cached tokens, and expose the new behaviour through FastAPI regression tests.
- Add coverage showing dynamic invariant options merge cleanly with additional
  static choices so TOML `options = ["...unique_values...", { value = "Other" }]`
  yields the expected select menu.
- Document the sentinel workflow in the README and `docs/demos/invariant_select_options.md`
  so route authors can adopt dynamic select lists without digging through tests.

## Local reference parser consolidation (work branch)

- Convert `_parse_local_reference` into a structured dataclass so `/local/resolve`
  shares explicit parsing semantics with helper callers instead of unpacking a
  positional tuple.
- Add unit tests that exercise multi-source column selection, prefix validation,
  and limit/offset propagation for local references.
- Extend the README section on `local:` references to document supported query
  parameters and integer coercion expectations.

## Chart.js vendor hardening (work branch)

- Add deterministic unit coverage for `ensure_chartjs_vendor` (existing asset reuse,
  environment skip, HTTP errors, write failures) plus the FastAPI helper that wires
  the vendored script into application state.
- Simplify the vendor result container to expose `prepared`/`skipped` flags instead
  of an unused filesystem handle and factor Chart.js setup into
  `server.app._prepare_chartjs_assets` for readability.
- Document air-gapped guidance in the README so operators pre-populate
  `storage_root/static/vendor/chartjs/` before disabling the download helper.
- Vendor the upstream Chart.js 4.4.3 build inside `webbed_duck.static.chartjs`
  so deployments without outbound network access can serve the asset directly
  from the installed package, and guard it with a regression test that asserts
  the script ships in wheels.

## Chart JS response format (work branch)

- Add a `chart_js` response that turns route `[[charts]]` specs into Chart.js
  canvases with share-aware headers and a vendored Chart.js runtime served from
  `/vendor/chart.umd.min.js`.
- Support `?embed=1` snippets and configurable script/canvas metadata via
  `[chart_js]` TOML or `@postprocess chart_js` overrides so downstream pages can
  embed charts without iframes while falling back to the CDN only when vendoring
  fails.
- Extend the README, changelog, and regression suite (postprocess, UI filters,
  README claims) to cover the new format and ensure the embed flow stays stable.

## Share attachment safeguards + compiler guardrails (work branch)

- Add regression tests covering share attachment size budgets, config parsing
  for email/share overrides, and compiler orphan `.sql` detection so future
  refactors preserve validation messages.
- Extract a helper inside `server.app` to centralise share attachment size
  enforcement, trimming duplication across raw and zipped responses.
- Document the global cache pagination knobs and share size limits in the README
  so operators configure limits intentionally instead of learning via runtime
  errors.

## Cache invariant casefold coverage (work branch)

- Add a FastAPI regression test proving case-insensitive invariant filters reuse
  cached pages and still return rows with their original casing.
- Factor invariant filter case-folding into a shared helper so cache key
  canonicalisation and runtime filtering rely on the same logic.
- Documented the lowercase normalisation for `case_insensitive = true` in the
  README alongside a reminder that DuckDB/FastAPI extras are required for the
  cache-heavy pytest suite.

## DuckDB failure guardrails + canonical route layout (work branch)

- Add a FastAPI regression test that forces a `duckdb.Error` during execution and
  asserts the server returns the documented 500 response payload.
- Convert the bundled `hello` sample into a TOML/SQL/MD triplet and regenerate
  the compiled artifact so contributors see the canonical layout instead of the
  deprecated combined Markdown format.
- Call out the refreshed sample in the README quick start to steer route authors
  away from legacy Markdown frontmatter files.

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

## Local runner reuse helper (work branch)

- Introduce `LocalRouteRunner` so repeated programmatic executions reuse cache
  and overlay stores instead of reinitialising on every call.
- Add unit coverage that exercises Arrow and records formats plus the legacy
  `run_route` convenience wrapper.
- Update README "Local execution" guidance to steer developers toward the new
  helper when building batch jobs or CLI tools.

## Route authoring guidance refresh (work branch)

- Rewrite the README around the new TOML + SQL route layout, covering
  dependency metadata, execution modes, and the compiler's former combined-Markdown
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
