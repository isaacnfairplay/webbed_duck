# TODO: Annotated Share Workflow Demo

- **Demo directory:** `demos/annotated-share/`
- **Scenario focus:** Showcase how WebDuck lets you annotate live data,
  preview the merged result locally, and fan it out through multi-format shares
  without leaving the intranet toolchain.
- **Automation requirements:**
  1. Compile a fresh workspace copy of the sample routes and enable overrides
     plus pseudo authentication for the run.
  2. Drive the FastAPI app via `TestClient` to authenticate, inspect the schema
     form metadata, submit an override, and create a share with multiple
     attachment formats.
  3. Capture a local `LocalRouteRunner` execution after the override lands so the
     transcript proves overlays affect offline workloads as well.
  4. Stub the outbound email adapter and report the captured subject, audience,
     and attachment filenames in the transcript.
  5. Fetch the share token payload to close the loop and verify the override is
     present in the delivered rows.
- **Artifacts to produce:**
  - `demos/annotated-share/generate_demo.py` automation entry point.
  - Auto-generated `demos/annotated-share/demo.md` built entirely from captured
    responses.

Avoid hand editing the generated transcript—rerun the generator after
behaviour changes.
