# Local Route Chaining Demo (Automation Placeholder)

See the generator requirements in `../../to-do/local-chaining-demo.md`.

Everything committed here must either drive or be emitted by an automated
generator. Plan for:
- A runnable entry point (for example `generate_demo.py`) that calls the real
  chaining APIs (`/local/resolve`, `LocalRouteRunner`, etc.) and records live
  outputs.
- An auto-generated `demo.md` rebuilt by that entry point with the captured
  command invocations, JSON payloads, and verification notes.
- Supporting fixtures or scripts needed to make the generator deterministic.

Avoid manually authored descriptions—run the generator again whenever the code
changes.
