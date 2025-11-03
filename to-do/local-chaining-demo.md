# TODO: Local Route Chaining Demo

- **Demo directory:** `demos/local-chaining/`
- **Scenario focus:** Demonstrate calling routes from other routes via `/local/resolve` and the Python `run_route` helper.
- **What the finished demo should include:**
  1. Example `curl` or HTTPie interactions with `/local/resolve` that show parameter overrides and response payloads.
  2. A Python REPL transcript using `LocalRouteRunner` or `run_route` to execute a secondary route without HTTP.
  3. Discussion of caching/validation behavior and how errors are surfaced when references are invalid.
  4. Suggestions for composing chained results into follow-on processing.
- **Artifacts to produce:** `demos/local-chaining/demo.md` mixing terminal transcripts, JSON snippets, and explanatory text.

Call out any configuration toggles (e.g., auth requirements) that must be satisfied before the chaining examples will run.
