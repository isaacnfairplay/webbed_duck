# Route Authoring & Serving Demo (Automation Placeholder)

See the generator requirements in `../../to-do/route-authoring-demo.md`.

Only automation scaffolding and produced artifacts belong here, such as:
- A generator entry point (for example `generate_demo.py`) that invokes the CLI
  commands, issues live HTTP requests, and captures their stdout/stderr along
  with response payloads.
- A generated `demo.md` file produced from those captures whenever the generator
  runs so the walkthrough stays trustworthy.
- Supporting fixtures required to reset build/runtime directories between runs.

Skip hand-authored prose—refresh `demo.md` by re-executing the generator.
