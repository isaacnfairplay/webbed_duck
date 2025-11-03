# TODO: Data Append Demo

- **Demo directory:** `demos/data-append/`
- **Scenario focus:** Capture how operators can append new rows through `/routes/{id}/append` and inspect the persisted CSV.
- **What the finished demo should include:**
  1. Steps to identify a route with `[append]` metadata and prepare a valid JSON payload.
  2. Sample POST requests (happy path and validation failure) highlighting required columns.
  3. File system inspection of the generated CSV under `runtime/appends/`, including discussion of headers and row structure.
  4. A follow-up fetch of the base route demonstrating how appended records appear in downstream views.
- **Artifacts to produce:** `demos/data-append/demo.md` documenting commands, payloads, and the resulting CSV excerpt.

Note any cleanup procedures to remove appended rows after the demo concludes.
