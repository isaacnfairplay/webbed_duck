# Security Guide

This project ships with runtime guardrails that are enforced by configuration
parsers, the route compiler, and the share workflow. The sections below outline
those existing defenses and how to keep them effective.

## Secrets, constants, and templated values
- Configuration parsing only accepts constant and secret tables that are
  dictionaries, rejects duplicates, and requires each secret to declare both a
  `service` and `username`. Paths are expanded, normalised, and validated as part
  of configuration loading to prevent implicit escapes or missing directories.
  【F:webbed_duck/config.py†L79-L139】【F:webbed_duck/config.py†L244-L318】
- Server storage and plugins directories are synchronised into runtime config
  and must exist on disk. Plugins directories containing Python packages are
  rejected, and both storage and plugins paths are resolved to absolute
  directories before use.【F:webbed_duck/config.py†L45-L117】
- Route constants may come from server-scoped settings, front matter `const`
  blocks, or templated `{{ route.constants.* }}` references. Each binding must be
  unique, secret references must point to keyring entries, and SQL templates are
  rewritten to parameter placeholders unless explicitly marked as identifiers.
  Secrets are only resolved when the optional `keyring` backend is available, and
  missing credentials raise compilation errors.【F:webbed_duck/core/compiler.py†L373-L475】【F:webbed_duck/core/compiler.py†L483-L515】

## Plugin sandboxing and loader hygiene
- Plugin paths are normalised to POSIX form, reject absolute segments, forbid
  `.`/`..`, and require `.py` suffixes. Callable names must be valid Python
  identifiers, preventing attribute traversal or dunder injection.
  【F:webbed_duck/plugins/loader.py†L20-L76】
- Loaded files are resolved under the configured plugins root. The loader
  refuses files outside that tree, enforces the absence of `__init__.py` sentinels
  to keep the directory non-package, and caches modules with digests to avoid
  stale code reuse. The root directory is created on-demand but must remain a
  plain folder without packages.【F:webbed_duck/plugins/loader.py†L78-L201】

## Share tokens, bindings, and redaction workflow
- Share tokens are generated with `token_urlsafe(32)`, hashed with SHA-256 for
  storage, and paired with per-record expirations derived from the configured
  TTL. Token resolution re-checks the hash, validates expiration, and prunes
  expired entries immediately.【F:webbed_duck/server/share.py†L21-L83】
- Optional share bindings hash the caller's user-agent and truncate IP prefixes
  before comparison. When enabled via configuration, both hashes must match the
  stored values; mismatches deny access without revealing token validity.
  【F:webbed_duck/server/share.py†L85-L140】
- Redaction requests are sorted and deduplicated before storage, guaranteeing a
  consistent policy for downstream consumers.【F:webbed_duck/server/share.py†L106-L139】

## Continuous enforcement
Run the following tools locally and in CI to keep security assumptions intact:

```bash
uv run ruff check .
uv run mypy --strict webbed_duck
uv run pytest
uv run radon cc webbed_duck -a
```

- Ruff enforces linting and import hygiene, including bans on ambiguous path
  handling.
- `mypy --strict` keeps type signatures honest, which is critical for ensuring
  secret dictionaries and plugin paths are validated before use.
- Pytest exercises runtime behaviours, including compiler error paths and share
  workflows.
- Radon complexity gating helps catch regressions that could hide security
  escapes inside overly complex flows.

## Quick-start remediation checklists

### Rotate stored secrets
1. Update the relevant `config.toml` secret entry with the new `service` or
   `username`, ensuring the key remains unique.【F:webbed_duck/config.py†L266-L318】
2. Refresh any route-level secret references to match the updated key; the
   compiler will fail fast if mismatches occur.【F:webbed_duck/core/compiler.py†L373-L475】
3. Redeploy with `uv run pytest` and `uv run mypy --strict webbed_duck` to verify
   the configuration parses and dependent routes still compile.

### Audit plugin directories
1. Ensure the configured plugins directory exists and contains no `__init__.py`
   files or sub-packages.【F:webbed_duck/config.py†L108-L118】【F:webbed_duck/plugins/loader.py†L150-L201】
2. Review each plugin path: files must reside under the root, use forward
   slashes, and end in `.py`. Reject any path containing `..` or backslashes.
   【F:webbed_duck/plugins/loader.py†L28-L76】
3. Invalidate loader caches after removing or updating plugins to avoid stale
   bytecode and confirm the loader revalidates paths.【F:webbed_duck/plugins/loader.py†L98-L149】

### Harden share bindings
1. Tune email configuration to require user-agent and/or IP prefix bindings for
   sensitive shares.【F:webbed_duck/config.py†L165-L190】
2. Verify the FastAPI layer captures `request.client` data so IP hashes are
   available, then run the test suite to ensure share resolution respects the new
   policies.【F:webbed_duck/server/share.py†L33-L139】

Keeping these checklists on rotation helps ensure secret storage, plugin loading,
and share links remain enforceable across releases.
