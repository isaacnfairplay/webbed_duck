# Annotated Share Demo (Guidance)

Combine pseudo-authenticated overrides with share redaction in a single,
repeatable script:

- Use the automation hooks to compile routes into an isolated runtime under
demos/annotated-share/runtime.
- Capture the pre-override state with `LocalRouteRunner` so the transcript shows
how overrides affect cached slices without re-running SQL.
- Apply an override through the HTTP API, confirm it flows into UI/JSON
responses, and then create a share that redacts the same column.
- Resolve the share token to prove the sanitized export omits the annotated
column while the local view keeps it.
- Clean up the SQLite meta store and overrides file at the end so reruns stay
idempotent.
