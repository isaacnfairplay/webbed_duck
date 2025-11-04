# TODO: Overrides & Annotations Demo

- **Demo directory:** `demos/overrides/`
- **Scenario focus:** Exercise the overrides API and surface the results through
  the UI using live calls, not static descriptions.
- **Automation requirements:**
  1. Implement a generator script (e.g., `generate_demo.py`) that seeds the
     necessary route data, submits override mutations, fetches audit trails, and
     captures evidence from the HTML renderer.
  2. Capture raw HTTP requests/responses, rendered HTML fragments/screenshots,
     and any rollback operations triggered during the run.
  3. Compose `demo.md` directly from those captures as part of the generator
     execution, overwriting prior content on each run.
  4. Include teardown logic that removes created overrides to keep the demo
     idempotent.
- **Artifacts to produce:**
  - `demos/overrides/generate_demo.*` (or equivalent automation entry point) and
    supporting fixtures.
  - Auto-generated `demos/overrides/demo.md` sourced exclusively from captured
    outputs.

Do not modify `demo.md` by hand—rerun the generator whenever behaviour changes.
