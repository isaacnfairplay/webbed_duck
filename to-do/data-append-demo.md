# TODO: Data Append Demo

- **Demo directory:** `demos/data-append/`
- **Scenario focus:** Execute the append workflow end-to-end so the resulting
  demo is generated from real runs rather than prose.
- **Automation requirements:**
  1. Author a generator script within the demo directory (e.g.,
     `generate_demo.py`) that resets the append storage, performs real
     `/routes/{id}/append` POSTs (happy path + validation failure), and reads the
     resulting CSV from `runtime/appends/`.
  2. Capture every command, payload, HTTP status, and filesystem snapshot from
     the live run; do not hard-code expected outputs.
  3. Render the captured artefacts into `demo.md` as part of the generator
     execution (overwrite on each run) so the file mirrors current behaviour.
  4. Include a cleanup step in the generator that restores the append storage to
     its pre-run state.
- **Artifacts to produce:**
  - `demos/data-append/generate_demo.*` (or equivalent entry point) plus
    supporting fixtures.
  - Auto-generated `demos/data-append/demo.md` built exclusively from captured
    outputs.

Manual edits to `demo.md` are not allowed—rerun the generator whenever the code
changes.
