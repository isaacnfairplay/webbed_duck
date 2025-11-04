# TODO: Local Route Chaining Demo

- **Demo directory:** `demos/local-chaining/`
- **Scenario focus:** Prove chaining behaviour by running the actual `/local/resolve`
  endpoint and local runner helpers, capturing their live outputs.
- **Automation requirements:**
  1. Build a generator script (e.g., `generate_demo.py`) that executes both HTTP
     and in-process chaining calls, exercising parameter overrides, cache hits,
     and error paths.
  2. Record the exact commands, inputs, and JSON responses emitted during the
     run—no mocked data or static transcripts.
  3. Emit `demo.md` directly from the generator by templating the captured data
     (overwrite on each run) so the walkthrough reflects reality.
  4. Ensure the generator configures any required feature flags/auth toggles and
     tears them down afterwards.
- **Artifacts to produce:**
  - `demos/local-chaining/generate_demo.*` (or similar automation entry point)
    plus helper modules.
  - Auto-generated `demos/local-chaining/demo.md` assembled from captured
    outputs.

Manual editing of `demo.md` is forbidden—rerun the generator to refresh the
scenario.
