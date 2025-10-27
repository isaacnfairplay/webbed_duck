# Branch-level Changelog

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
