# TODO: Pseudo Auth & Sharing Demo

- **Demo directory:** `demos/pseudo-auth/`
- **Scenario focus:** Walk through the pseudo-session lifecycle and trigger a share request guarded by that session.
- **What the finished demo should include:**
  1. Configuration notes for enabling `auth.mode = "pseudo"` and restarting the server.
  2. HTTP examples for creating, inspecting, and deleting a pseudo session (capturing cookies).
  3. A share submission that reuses the issued cookie and highlights the returned metadata/artifacts.
  4. Optional tie-in with `/local/resolve` to demonstrate how share validation mirrors internal chaining.
- **Artifacts to produce:** `demos/pseudo-auth/demo.md` featuring configuration snippets, HTTP transcripts, and guidance on cleaning up sessions/shares.

Emphasize security caveats (trusted networks, non-production usage) to mirror the README positioning.
