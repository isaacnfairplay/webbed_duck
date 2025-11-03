# Testing Conventions

This guide establishes the shared expectations for writing and organising tests in `webbed_duck`. Adhering to these conventions keeps the suite predictable, fast, and self-documenting.

## Docstrings & Narratives

- **Fixture docstrings** should describe the lifecycle and cleanup semantics (e.g., "Yields a DuckDB connection backed by a temporary file").
- **Test modules** start with a module-level docstring summarising the behaviour slice under test when the filename is not self-evident.
- **Parametrised tests** include inline comments or docstrings clarifying non-obvious parameter choices, especially when mirroring tricky SQL edge cases.
- Prefer **imperative mood** for short docstrings ("Configure", "Yield") and keep them under 88 characters per line to match the repository formatting norms.

## Dataset Placement

- Synthetic datasets that are *route specific* live beside their corresponding test module under `tests/`, using a `_data/` suffix directory when multiple files are required.
- Shared CSV/Parquet fixtures that model platform-wide behaviours belong under `tests/server/fixtures/` to make reuse explicit.
- Temporary, generated-at-runtime datasets should flow through helpers in `tests/utils/storage.py` rather than being checked into version control.
- When datasets are large or compressed, include a README stub in the fixture directory outlining generation steps to keep provenance transparent.

## Result Expectations & Assertions

- Use the `duckdb_connection` fixture for assertions that rely on SQL output so pragmas and cleanup remain consistent across modules.
- Mark long-running or orchestration-heavy checks with `@pytest.mark.integration` and, where relevant, gate DuckDB-heavy flows behind `@pytest.mark.duckdb`.
- Hypothesis-based tests should import the shared profiles declared in `tests/conftest.py`; override settings locally only when tighter bounds are necessary for correctness.
- When asserting on tabular output, favour Arrow schema comparisons or DuckDB `DESCRIBE` metadata before checking raw row tuples to reduce brittleness.
- Document the **expected side effects** (files written, routes generated) in assertion messages so failures highlight the intent.

Following these patterns keeps developer velocity high while ensuring the suite continues to offer actionable diagnostics for regressions.

## Coverage updates — March 2025

- Added `tests/compiler/` modules that stress the directive payload collectors, parameter merging, preprocess normalisation, cache metadata helpers, and SQL placeholder rewrites. Property-based cases (skipped automatically when Hypothesis is unavailable) now exercise edge combinations of directive payloads and cache declarations that previously required manual reproduction.
- Introduced `tests/execution/` with lightweight `RouteExecutor` fixtures covering relation execution, invariant-aware caching, parquet dependency registration, and recovery paths after dependency failures. The suite also wires the optional `pytest-benchmark` fixture to ensure we can benchmark cached executions without additional harness glue.
- Known limitation kept for triage: routes that enable invariant filters remain incompatible with `parquet_path` dependencies. The new failure-mode regression test documents the behaviour until a safe orchestration strategy is designed.
