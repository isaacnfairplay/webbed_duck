# Parameter Forms & Progressive UI Demo (Automation Placeholder)

See the generator requirements in `../../to-do/parameter-forms-demo.md`.

Commit only the automation and produced artifacts, such as:
- A generator script (for example `generate_demo.py`) that drives browserless and
  JavaScript-enabled flows, captures the rendered HTML/screenshots directly from
  the running app, and verifies metadata flags by executing real requests.
- The generated `demo.md` output built from those captured assets and refreshed
  whenever the generator runs.
- Deterministic fixtures (e.g., HTML snapshot tooling) that keep the run
  repeatable.

Manual write-ups are out of scope—regenerate the outputs whenever behaviour
changes.
