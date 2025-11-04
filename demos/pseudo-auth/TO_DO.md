# Pseudo Auth & Sharing Demo (Automation Placeholder)

See the generator requirements in `../../to-do/pseudo-auth-demo.md`.

All committed assets must participate in or result from automated execution:
- Provide a generator entry point (e.g., `generate_demo.py`) that configures
  pseudo auth, drives the HTTP flows end-to-end, and captures real cookies,
  responses, and cleanup steps.
- Rebuild `demo.md` from the generator so the documented flows always match the
  latest runtime behaviour.
- Include any helper modules or fixtures necessary to keep the run reproducible
  and isolated.

Manual narratives are prohibited—rerun the generator to refresh outputs.
