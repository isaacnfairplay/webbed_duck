# Step 0 — Baseline & safety scaffold

## Security baseline
- Captured the runtime guardrails (secrets enforcement, plugin sandboxing, share-token hygiene, and continuous tooling expectations) in [`SECURITY.md`](../SECURITY.md) so reviewers can verify configuration, loader, and share workflows quickly.
- Documented the mandatory local/CI checks (Ruff, `mypy --strict`, pytest, and radon) alongside the security guidance to anchor Step 0's verification surface.

## Legacy module guidance
- Introduced consistent DeprecationWarning banners and docstring guidance for `webbed_duck.core` import surfaces (`compiler`, `incremental`, `local`, and `routes`) and their primary entry points, pointing users toward the forthcoming engine package and exercising the behaviour in `tests/test_core_deprecations.py`.
- README-side reminders remain in place to replace any remaining legacy `.sql.md` sidecars with canonical TOML/SQL pairs, keeping the migration queue visible for later steps.

## Quality gate status
| Check | Result | Notes |
| --- | --- | --- |
| `uv run ruff check .` | ✅ | Passes with an advisory about an invalid `# noqa` rule in `tests/test_executor_params.py`, but linting otherwise succeeds. |
| `uv run mypy --strict webbed_duck` | ❌ | Blocks on 132 errors: missing stubs for `pyarrow`, unchecked `Any` returns, incompatible numeric coercions, and stale `type: ignore` directives across server/cache/compiler modules. |
| `uv run pytest` | ❌ | Fails `tests/test_packaging.py::test_wheel_contains_webbed_duck_package` (virtualenv lacks `pip`) and `tests/test_readme_claims.py::test_readme_statements_are_covered` (README tool list not aligned with installed tooling). |
| `uv run radon cc webbed_duck -a` | ❌ | Command fails because `radon` is not provisioned inside the UV environment; complexity snapshot captured separately via `uvx radon` while we queue a tooling fix. |
| `uv run ruff check webbed_duck/core` | ✅ | Targeted lint for the deprecated core surface passes after inserting the warning scaffolding. |
| `uv run pytest tests/test_compiler.py tests/test_local_runner.py` | ✅ | Core compiler/local smoke tests pass with deprecation warnings downgraded via `conftest.py` filters. |
| `uv run pytest tests/test_core_deprecations.py` | ✅ | New regression suite asserts that package imports and entry points emit the expected DeprecationWarnings. |
| `uv run mypy --strict webbed_duck/core` | ❌ | Still blocked by the wider repository typing backlog (pyarrow stubs, cache typing, etc.); no new core-specific regressions introduced by the warnings. |

## Complexity budget
- Average cyclomatic complexity: **B (5.56)** (measured via `uvx radon cc webbed_duck -a`), forming the baseline for future deltas.
- Legacy-core subset complexity: **B (6.70)** via `uvx radon cc webbed_duck/core -a`, a +1.14 uptick driven by the additional warning helpers and test scaffolding that accompany the deprecation rollout.
- Complexity delta vs. pre-Step 0: **±0.00** (first measured baseline).
- Hotspot mitigations queued: refactor the parameters form renderer and route mapping loader before adding new logic to those modules.

## Risk tracking & follow-ups
- Provision radon via project tooling (or vendor it through `uv`) so `uv run radon` can resolve without manual intervention.
- Restore wheel-building prerequisites (ensure `pip` is available inside the managed venv) to unblock packaging tests.
- Introduce typing backfills or protocol wrappers for pyarrow-heavy paths to clear the strict MyPy gate.
- Align README tooling guarantees with the actual dependency set to keep documentation and enforcement in sync.

## Complexity automation scaffolding (current branch)
- Added `scripts/update_complexity_history.py` to snapshot Radon complexity output via `uvx` and regenerate a Mermaid-backed
  history markdown (`docs/complexity_history.md`) with grade distributions, hotspot tables, and diff commentary for the tracked
  widgets modules.
- Extended `.github/workflows/version-bump.yml` to install `uv`, execute the complexity snapshotter during automated version
  bumps, and commit the refreshed history alongside the version files so mainline complexity metrics evolve with each release.
- Seeded the history with the current baseline (average cyclomatic complexity **B / 5.565**), documenting the outstanding
  high-complexity blocks called out by the grading tool for future refactors.
- Ensured Matplotlib ships with the UV dev dependency group so the chart renderer is present when `uv run` executes the
  complexity history script in automation.
