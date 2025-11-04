# TODO: Pseudo Auth & Sharing Demo

- **Demo directory:** `demos/pseudo-auth/`
- **Scenario focus:** Execute the pseudo-session lifecycle and share flow for
  real, capturing live cookies and responses.
- **Automation requirements:**
  1. Deliver a generator script (e.g., `generate_demo.py`) that switches the
     config to pseudo auth, restarts/bootstraps the server as needed, and runs
     the create/inspect/delete session calls alongside a share submission.
  2. Record raw HTTP requests, headers, cookies, and returned metadata/artifacts
     straight from the run (including optional `/local/resolve` validations).
  3. Emit `demo.md` programmatically from the captured results, overwriting the
     file each time.
  4. Enforce teardown in the generator so sessions/shares are removed or expire
     at the end of the script.
- **Artifacts to produce:**
  - `demos/pseudo-auth/generate_demo.*` (or comparable automation entry point)
    and any helper fixtures.
  - Auto-generated `demos/pseudo-auth/demo.md` written solely from captured
    outputs.

Never manually edit `demo.md`; refresh it by rerunning the generator. Retain the
securable-network caveats within the generated output.
