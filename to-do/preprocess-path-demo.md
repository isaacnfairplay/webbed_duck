# TODO: Preprocess Path Reference Demo

- **Demo directory:** `demos/preprocess-path-callable/`
- **Scenario focus:** Demonstrate `callable_path` + `callable_name` resolving a
  local Python file without packaging or installation, and capture the resulting
  route execution.
- **Automation requirements:**
  1. Build a generator (`generate_demo.py`) that writes the plugin file to a
     workspace, compiles the demo route, and executes it through
     `LocalRouteRunner`.
  2. Produce `demo.md` straight from the generator with timestamps, the commands
     invoked, and the returned data proving the preprocessor ran.
  3. Keep the generator idempotent: clean or recreate its workspace on every run
     so contributors can refresh the transcript by re-running the script.
- **Artifacts to produce:**
  - Auto-generated `demo.md` containing the transcript.
  - Route sources plus the plugin file used by the demo.

Re-run the generator after any change so `demo.md` stays in sync.
