# TODO: Route Authoring & Serving Demo

- **Demo directory:** `demos/route-authoring/`
- **Scenario focus:** Validate compile/serve flows and response formats by
  executing the real CLI and HTTP clients.
- **Automation requirements:**
  1. Provide a generator script (e.g., `generate_demo.py`) that runs
     `webbed-duck compile`, boots `webbed-duck serve`, and issues HTTP requests
     for HTML/CSV/Arrow responses while the server is live.
  2. Capture stdout/stderr, HTTP payloads, and any ancillary files created
     during the run without faking the results.
  3. Assemble `demo.md` from those captures inside the generator (overwrite on
     each execution) so the walkthrough is guaranteed accurate.
  4. Reset build/runtime directories before and after the run to keep the script
     idempotent.
- **Artifacts to produce:**
  - `demos/route-authoring/generate_demo.*` (or similar entry point) plus helper
    modules to manage process lifecycle.
  - Auto-generated `demos/route-authoring/demo.md` sourced solely from captured
    outputs.

Never edit `demo.md` manually—rerun the generator to refresh assumptions and
documented behaviour.
