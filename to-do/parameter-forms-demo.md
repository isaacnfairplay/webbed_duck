# TODO: Parameter Forms & Progressive UI Demo

- **Demo directory:** `demos/parameter-forms/`
- **Scenario focus:** Demonstrate progressive enhancement by generating assets
  from an executable run that toggles JavaScript and inspects metadata.
- **Automation requirements:**
  1. Ship a generator script (e.g., `generate_demo.py`) that starts the app,
     captures HTML snapshots of the `/hello` form with and without JavaScript,
     and records the responses for multiple parameter sets.
  2. Gather network traces or CLI outputs directly from the run to prove how
     `show_params`, `invariant_filters`, pagination, etc. behave.
  3. Produce `demo.md` automatically from the captured assets, overwriting the
     file every time the generator executes.
  4. Export artefacts (screenshots, HAR files, etc.) deterministically so the
     demo can be regenerated in CI/locally without manual intervention.
- **Artifacts to produce:**
  - `demos/parameter-forms/generate_demo.*` (or similar automation entry point)
    plus capture helpers.
  - Auto-generated `demos/parameter-forms/demo.md` assembled exclusively from
    the recorded outputs.

Never hand-edit `demo.md`; re-run the generator to refresh it.
