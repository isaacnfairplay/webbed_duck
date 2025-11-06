# TODO: Preprocess Module Reference Demo

- **Demo directory:** `demos/preprocess-module-callable/`
- **Scenario focus:** Show how `callable_module` + `callable_name` resolve
  preprocessors from a Python package without installing it globally, and prove
  the compiler validates the reference before runtime.
- **Automation requirements:**
  1. Provide a generator script (`generate_demo.py`) that adds the demo package to
     `sys.path`, compiles the routes, and captures real outputs from
     `LocalRouteRunner` to confirm the module-backed preprocessor executed.
  2. Emit `demo.md` from the generator with timestamps, the captured commands, and
     the resulting rows.
  3. Ensure the generator rebuilds routes inside an isolated workspace so the
     demo is rerunnable without manual cleanup.
- **Artifacts to produce:**
  - Auto-generated `demo.md` describing the compile and run steps.
  - The demo package and route sources used by the generator.

Always refresh `demo.md` by re-running the generator after changing code.
