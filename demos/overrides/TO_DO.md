# Overrides & Annotations Demo (Automation Placeholder)

See the generator requirements in `../../to-do/overrides-demo.md`.

Only automated assets belong here. Expect to add:
- A runnable generator (e.g., `generate_demo.py`) that drives override creation,
  listing, and rollback flows against the live server/runtime while capturing
  exact HTTP requests and responses.
- A generated `demo.md` built from those captured outputs whenever the
  generator runs.
- Supporting fixtures (temporary datasets, snapshot utilities, etc.) required to
  keep the run reproducible.

Do not hand-craft narrative files; refresh `demo.md` by rerunning the
generator.
