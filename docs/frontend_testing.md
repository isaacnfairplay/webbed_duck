# Front-end Testing Strategy

The UI layer now ships with automated coverage for JavaScript behaviours, HTML
widgets, and shared CSS tokens. The test harness intentionally mirrors our
Python-oriented workflow so that contributors can verify both stacks with a
single `pytest && npm test` cycle.

## Why Vitest + jsdom?

* **Fast, isolated modules.** The UI scripts are authored as native ES modules.
  [Vitest](https://vitest.dev/) executes those files directly without a build
  step and exposes an ergonomic mocking API similar to `pytest` fixtures.
* **Browser-like DOM semantics.** The bundled `jsdom` environment allows us to
  exercise event handlers (`click`, `input`, `scroll`, etc.) in memory while
  stubbing browser primitives such as `matchMedia`, `localStorage`, and
  `requestAnimationFrame`.
* **Compatibility with Testing Library.** `@testing-library/dom` helps verify
  accessibility attributes (`aria-expanded`, focus management) using the same
  conventions we follow in Python snapshot tests.
* **Coverage integration.** Vitest emits an lcov report so CI tooling can track
  JavaScript coverage alongside the existing Python reports.

## Covered scenarios

| Area | Tests | Highlights |
|------|-------|------------|
| Header controls | `frontend_tests/header.spec.ts` | Collapsing the sticky header, toggling filters, and persisting the new theme switcher state (including system reset via `Alt+Click`). |
| Multi-select widget | `frontend_tests/multi_select.spec.ts` | Synchronises checkbox selections with the hidden `<select>`, tunes panel height against viewport changes, and exercises the search/filter workflow. |
| Chart boot loader | `frontend_tests/chart_boot.spec.ts` | Ensures the Chart.js loader resolves exactly once per source URL and that canvases bootstrap when configuration JSON is present. |
| Shared CSS tokens | `frontend_tests/styles.spec.ts` | Guards the light/dark theme variables, form colour palette, and multi-select sizing hooks. |

## HTML + CSS integration checks

The Vitest suite validates DOM mutations, but we still assert on the generated
HTML server-side to guarantee templates stay in sync:

* `tests/test_ui_theme_toggle.py` confirms every rendered page emits the theme
  toggle button and the `data-has-top` flag.
* Existing UI tests (e.g. `tests/test_ui_header_behavior.py`) continue to spawn
  Node subprocesses to execute the real browser modules against compiled routes.

Together these tests give us confidence that Jinja-generated HTML, CSS tokens,
JavaScript behaviours, and Python renderers evolve together.
