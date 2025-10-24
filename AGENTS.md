# AGENTS.md v2

## Project: `webbed_duck`

### A Parameterized SQL Web Server for DuckDB, built for Intranets — **securable** by design

> `webbed_duck` converts Markdown+SQL route files into fast, auditable, intranet-friendly APIs and HTML views backed by DuckDB and Apache Arrow.
> It is **securable** (not “secure”): designed for trusted networks with clear, modular hardening paths (proxy TLS, external auth, token binding, PII redaction).
> This document is the master guide for human/AI maintainers: architecture, compiler, plugins, testing, security posture, DX, and progress trackers.

---

## 0) Contents

* [1) Philosophy & Invariants](#1-philosophy--invariants)
* [2) Architecture & Data Flow](#2-architecture--data-flow)
* [3) Repository Layout & Storage Roots](#3-repository-layout--storage-roots)
* [4) Configuration Surface](#4-configuration-surface)
* [5) Markdown Route Compiler (mdsql → Python)](#5-markdown-route-compiler-mdsql--python)
* [6) Request Lifecycle](#6-request-lifecycle)
* [7) DuckDB & Arrow Rules](#7-duckdb--arrow-rules)
* [8) Route Types (Static / Parametric / Virtual Views)](#8-route-types-static--parametric--virtual-views)
* [9) Parameters, Types, Guards & Preprocessors](#9-parameters-types-guards--preprocessors)
* [10) Postprocessors (HTML_T, HTML_C, Feed, Arrow RPC, Charts)](#10-postprocessors-html_t-html_c-feed-arrow-rpc-charts)
* [11) Static Asset Plug-in (Image Getter)](#11-static-asset-plug-in-image-getter)
* [12) Annotations, Tasks & Overrides (Overlay)](#12-annotations-tasks--overrides-overlay)
* [13) Sharing (Links + Email: Inline/Attachments)](#13-sharing-links--email-inlineattachments)
* [14) Auth & Sessions (Pseudo/Basic/External)](#14-auth--sessions-pseudobasicexternal)
* [15) Transport (HTTP-first; TLS via Proxy)](#15-transport-http-first-tls-via-proxy)
* [16) Incremental & Orchestrated Routes](#16-incremental--orchestrated-routes)
* [17) Internal API Chaining (“local:” routes)](#17-internal-api-chaining-local-routes)
* [18) Introspection, Auto-Forms & Static Pages](#18-introspection-auto-forms--static-pages)
* [19) Popularity Analytics & Folder Indexes](#19-popularity-analytics--folder-indexes)
* [20) Error Taxonomy & Mapping](#20-error-taxonomy--mapping)
* [21) Plugin Lifecycle & Extension Points](#21-plugin-lifecycle--extension-points)
* [22) CLI & Developer Experience](#22-cli--developer-experience)
* [23) Testing Strategy & Coverage](#23-testing-strategy--coverage)
* [24) Performance Notes & Limits](#24-performance-notes--limits)
* [25) Progress Trackers (Checklists & Mermaid Gantt)](#25-progress-trackers-checklists--mermaid-gantt)
* [26) Release, Versioning & Deprecations](#26-release-versioning--deprecations)
* [27) Appendices (Config, Examples, Snippets)](#27-appendices-config-examples-snippets)

---

## 1) Philosophy & Invariants

**Securable, not “secure”.** Default for intranets; provide guardrails and easy hardening.
**Predictable.** One DuckDB connection per request; no global cursors.
**Auditable.** Per-request IDs, redacted params, elapsed, rows, route/version.
**Static-first.** Production serves **compiled** routes from `routes_build/` (no decorators in prod).
**Arrow everywhere.** In-memory interchange is Arrow Tables or Streams only.

**Never violate:**

* Do not share DuckDB connections across requests/threads.
* Do not execute untrusted code. Route preprocessors are repo-managed, trusted artifacts.
* Do not persist plaintext tokens/passwords; share tokens stored hashed.
* Do not allow path traversal/symlink escape from `storage_root`.

---

## 2) Architecture & Data Flow

```mermaid
flowchart LR
  A["Client Browser/API"] -->|params| B["HTTP Server"]
  B --> C["Preprocessors (trusted, sandboxed)"]
  C --> D["DuckDB (per-request)"]
  D -->|Arrow Table| E["Postprocessors"]
  E -->|HTML / CSV / Parquet / Arrow| A
  B --> G["Auth Adapter (sessions)"]
  B --> H["Share Adapter"]
  E --> I["Asset Getter (images)"]
  B --> J["Overlay Storage (annotations/overrides)"]
  B --> K["Introspection / Schema Cache"]
```

**Storage root** (all internal paths derive from here):

```
storage_root/
  routes_build/            # compiled modules
  cache/                   # materialized artifacts (parquet/csv/html)
  schemas/                 # Arrow schemas (json)
  static/                  # system_theme.css/js, localized images
  runtime/
    meta.sqlite3           # sessions, shares, analytics (ref adapter)
    checkpoints.duckdb     # incremental progress (optional)
    auth.duckdb            # pseudo/basic auth (ref adapter)
```

---

## 3) Repository Layout & Storage Roots

```
webbed_duck/
  core/                    # DuckDB + Arrow + config + schema cache
  server/                  # HTTP app, routing, middleware
  plugins/                 # postprocessors, charts, assets, share adapters
  routes_src/              # *.sql.md sources
  routes_build/            # compiled *.py (prod source of truth)
  examples/                # emailer, share rendering, sample routes
  tests/                   # pytest suites
  config.toml              # runtime config (env override)
  pyproject.toml           # packaging
```

**Shared DBs across requests = SQLite** (sessions/shares/analytics/overlays).
**Query execution = per-request DuckDB**; file artifacts via DuckDB writers.

---

## 4) Configuration Surface

```toml
[server]
storage_root = "./storage"
theme = "system"                      # system | light | dark

[transport]
mode = "insecure_http"                # or "tls_terminated_proxy"
trusted_proxy_nets = ["127.0.0.1/32","10.0.0.0/8"]

[ui]
show_http_warning = true              # admins/devs may hide

[auth]
mode = "pseudo"                       # none | pseudo | basic_pseudo | external
allowed_domains = ["example.local"]
session_ttl_minutes = 45
remember_me_days = 14
cookie_name = "duckserv_sid"

[email]
adapter = "custom:examples.emailer.send_email"
from_address = "no-reply@example.local"
share_token_ttl_minutes = 90
bind_share_to_user_agent = true
bind_share_to_ip_prefix = true

[share]
max_total_size_mb = 15
zip_attachments = true
zip_passphrase_required = false
watermark = true

[cache]
ttl_hours = 24                        # default; routes can override “forever”

[analytics]
enabled = true
weight_interactions = 3

[feature_flags]
annotations_enabled = true
comments_enabled = true
tasks_enabled = true
overrides_enabled = true

[assets]
default_image_getter = "static_fallback_getter"  # overridable per route
```

---

## 5) Markdown Route Compiler (mdsql → Python)

**Route file sections** (`*.sql.md`):

* `@meta` (required): `id`, `version`, `default_format`, `allowed_formats`
* `@params`: types, required, coercions, guards (e.g., `path root:...`)
* `@preprocess`: ordered list of preprocessors
* `@postprocess`: per-format options (e.g., `html_c.image_col`)
* `@assets`: image getter selection & hints (base paths)
* `@charts`: declarative chart specs (see §10)
* `@overrides`: columns allowed to be overridden via overlay
* `@feed`: optional mapping for feed view (title/subtitle/date_col)
* SQL body with DuckDB **named parameters** (`:param`) and safe helper `{{lit_list:param}}`.

**Compiler pipeline**

1. Parse sections and SQL body.
2. Validate param schema; resolve processors.
3. Emit `routes_build/<route_id>_v<version>.py` with:

   * `execute(params) -> duckdb.Relation`
   * `schema() -> Arrow schema (cached)`
   * `render(format, relation|table, params) -> bytes|str`
4. Write `schemas/<route>_v<version>.json`.
5. Dev: hot reload; Prod: load only from `routes_build/`.

**Prod policy:** *No decorators in prod.* Decorators may exist in dev-only utilities.

---

## 6) Request Lifecycle

1. **Route match**: `/query/{route_id}.{format}?params` or `/v_{format}/{route_id}?params`.
2. **Auth**: resolve session/user (email, user_id, roles).
3. **Param parse & coercion**: types, defaults, guards.
4. **Preprocess**: trusted functions in restricted namespace (no FS/subproc).
5. **Execute**: new DuckDB connection → named-parameter query → Relation.
6. **Overlay**: merge annotations/overrides (if enabled).
7. **Postprocess**: HTML/CSV/Parquet/Arrow RPC; charts; assets localized.
8. **Cache**: write artifact per TTL policy.
9. **Respond**: stream/file; set cache headers.
10. **Log**: structured entry with timing, rows, redacted params.

---

## 7) DuckDB & Arrow Rules

* Python **3.12/3.13**, DuckDB **≥ 1.4**.
* **Never** share connections across requests; open per request.
* Convert with `relation.arrow_table()` (**not** `.arrow()`—batch semantics differ across versions).
* Write artifacts using DuckDB writers: `relation.write_parquet(path)`, `relation.write_csv(path)`.
* Internal interchange: **Arrow Table** to postprocessors, charts, overlays.
* Streaming **Arrow RPC** for virtual views (optional format).
* If a database is shared across requests, make it **SQLite**, not DuckDB.

---

## 8) Route Types (Static / Parametric / Virtual Views)

**Static routes (param-free).** Serve static HTML pages (docs/help/dash shells) under `/static` or `routes_src/static/`.

**Parametric routes.** Canonical `/query/{route_id}.{format}` with named params. Default formats: `parquet`, `csv`, `html_t`, `html_c`, `arrow_rpc`. *(JSON is optional via plugin; not default.)*

**Virtual viewers.** `v_html_t`, `v_html_c`, `v_feed`:

* Client-side virtualized scrolling; server applies `LIMIT/OFFSET` & column projection.
* Arrow slices preferred for transport (`arrow_rpc` endpoint).

**Folder index & navigation.**

* If a path is a folder and has no params, auto-generate an index of child routes and “go up” navigation.
* Popularity-weighted ordering (feature-flag-controlled).

---

## 9) Parameters, Types, Guards & Preprocessors

**Types**: `int`, `double`, `varchar`, `bool`, `date`, `timestamp`, `list[T]`, `path` (guarded).
**Coercions**: `coerce: csv` for `"a,b"` → `["a","b"]`; `coerce: intlist`, etc.
**Guards**:

* **Path** params must be under declared roots; normalize; reject `..` and symlinks.
* **Enum** values validated against allowlists (literal or via a supporting query).

**Preprocessors**: pure functions:

```python
def ensure_range(params: dict) -> dict:
    if not params.get("end_date"):
        params["end_date"] = params["start_date"]
    return params
```

* Run prior to SQL bind; **trusted code** (repo-managed), restricted namespace (no `open`, no `subprocess`, no network).
* Heavy data transforms should remain in SQL (DuckDB vectorization).

**SQL safe helpers**

* `{{lit_list:param}}` renders a safe literal list for `IN (...)`.
* All other values bound as **named parameters**.

---

## 10) Postprocessors (HTML_T, HTML_C, Feed, Arrow RPC, Charts)

**HTML_T (table).**

* Standards-compliant `<table>`; sticky header; truncation notice for very large results; system theme CSS; optional sorting.
* Optional renderers: link columns (`a`), image columns (via image getter).

**HTML_C (cards).**

* Mobile-first card grid; mappings via route metadata:

  * `image_col`, `title_col`, `meta_cols[]`

**Feed.**

* Time-ordered digest (e.g., defects, events) with grouping (Today/Yesterday/Older).
* Infinite scroll via virtual viewer.

**Arrow RPC.**

* `application/vnd.apache.arrow.stream` endpoint with `limit`, `offset`, `columns`.

**Charts (declarative).**
Route block:

```sql
--@charts:
--  - id: trend
--    type: line
--    x: date
--    y: defect_rate
--    group: model
```

* Default renderer: server-side **SVG** via local matplotlib (no external CDNs).
* Register custom renderers:

```python
@register_chart_renderer("line")
def render_line(table: pa.Table, spec: dict) -> str:  # returns SVG string
    ...
```

* Charts are embedded in HTML_T/HTML_C output; small UI toggles included.
* Performance: pre-aggregate in SQL; limit unique series; cap point counts.

---

## 11) Static Asset Plug-in (Image Getter)

**Goal:** let routes embed images whose paths must be localized/copied to server cache or mapped to `/static`.

Route hints:

```sql
--@assets:
--  image_getter: localize_images
--  base_path: "G:/LOCALDB/images"
```

Register getters:

```python
from webbed_duck.plugins.assets import register_image_getter

@register_image_getter("localize_images")
def localize_images(name: str, route_id: str) -> str:
    # copy/map external asset into storage_root/static/cache
    # return web path: "/static/cache/<uuid>.webp"
    ...
```

Rules:

* Normalize paths; deny `..` and symlinks.
* No network access by default; adapters may opt-in.
* Fallback getter: `/static/{name}`.

---

## 12) Annotations, Tasks & Overrides (Overlay)

**Why:** discussions, todos, and field corrections without mutating source data.

* **Row identity**: route declares `key` columns or compiler derives a canonical `row_key` JSON.
* **Overlay store** (adapter-owned schema): `(route_id, version, row_key, column, value_json, reason_code, author_hash, created_ts)` plus comments/tasks tables.
* **Per-cell override**: effective value = `COALESCE(override.value, base.value)`.
* **Audit**: store `actor_user_id` and **email hash**; UI masks emails by default.
* **ACLs**: route `@overrides.allowed` restricts which columns can be changed.
* **Propagates** to downstream views invoking the same route (+params).

Optional features (flagged): comment threads, task assignment (to registered users), and “share view to email”.

---

## 13) Sharing (Links + Email: Inline/Attachments)

**Links:**

* Create token → store **sha256(token)** + metadata.
* TTL (default 90m), single-use, bound to UA and optional IP prefix.
* Requires login (pseudo/basic/external) before resolving to live view; permissions `"view" | "comment" | "annotate" | "override"` (subset of route ACLs).

**Email:**

* Inline HTML snapshot (watermarked; row cap) + optional attachments (Parquet preferred; CSV; standalone HTML).
* Size cap; auto-zip; optional AES passphrase (not stored).
* PII redaction: drop/mask columns from route denylist; mask authors.
* Pluggable `EmailAdapter` (example with DummySMTP in `examples/emailer.py`).

UI: Single “Share” dialog with **Link** and **Email** tabs; include checkboxes for annotations, PII redaction, watermark.

---

## 14) Auth & Sessions (Pseudo/Basic/External)

Modes:

* `none`: anonymous
* `pseudo`: **email-only** (domain-allowlist); passwords disabled (default on HTTP)
* `basic_pseudo` (opt-in on HTTP intranet): email + password (argon2id/bcrypt), only from allowlisted subnets; rate-limited & locked out on abuse
* `external`: delegate to custom adapter (e.g., reverse proxy auth/OIDC/LDAP)

Sessions:

* Server-side (SQLite default); cookie: `HttpOnly`, `SameSite=Lax`; `Secure` flag auto from transport mode.
* Rolling expiry; remember-me capped in HTTP mode.
* User directory keyed by email; stable `user_id` for audit; migration preserves history across auth modes.

---

## 15) Transport (HTTP-first; TLS via Proxy)

* `transport.mode = "insecure_http"` by default; intended for intranet/VPN/VLAN.
* UI **warning banner** by default; admins may disable via `ui.show_http_warning=false`.
* To enable TLS: deploy reverse proxy (Caddy/NGINX) and switch to `tls_terminated_proxy`; cookies flip `Secure=true` and server enforces `X-Forwarded-Proto=https` from trusted proxies.
* Without TLS: keep share TTL short; bind tokens to UA/IP; prefer **no passwords** unless `basic_pseudo` explicitly enabled for intranet subnets.

---

## 16) Incremental & Orchestrated Routes

**Use case:** process day-by-day or ranges with checkpoints.

* Checkpoint DB: `runtime/checkpoints.duckdb` (or adapter-defined).
* Route hint:

```sql
--@incremental:
--  key: "date"        # column to iterate
--  batch: "1d"        # or “range” driven by params
```

* CLI emits next cursor and persists progress:

```
webbed_duck run-incremental shipping.by_date --start 2025-01-01 --end 2025-01-31
```

* Cache: per-batch artifacts (Parquet partitions); a separate roll-up route can query partitions.

> Scheduling/orchestration can be external (CRON/Airflow). We expose “next cursor” primitives.

---

## 17) Internal API Chaining (“local:” routes)

Invoke routes **without HTTP**, reusing validation and cache:

```python
from webbed_duck.core.local import run_route

table = run_route("inventory.current", params={"model": ["A","B"]}, format="arrow")
```

* Returns Arrow Table or materializes Parquet into cache.
* Preprocessors & overlays apply; auth context may be required.

---

## 18) Introspection, Auto-Forms & Static Pages

**Introspection endpoints**

* `GET /routes` → list id/version, description, popularity (if enabled).
* `GET /routes/{id}/schema` → param schema (types/defaults) & result schema (Arrow) with sample.

**Auto-forms**

* Render controls from param schema:

  * scalar → input; date/datetime pickers
  * list/enums → multi-select; options may be bound to a “choices query”
  * path → constrained picker under allowed roots
* Virtual views include auto-form by default (can be customized or replaced by static HTML).

**Static pages**

* Serve fixed HTML files as routes for docs/help/landing; no params.

---

## 19) Popularity Analytics & Folder Indexes

* If `analytics.enabled=true`, track per route:

  * `hits`, `rows_returned`, `avg_latency_ms`, `interactions (comments/overrides)`
* Folder indexes sort by popularity; toggleable.
* Store **hashed** user refs; never log PII at INFO.

---

## 20) Error Taxonomy & Mapping

| Category        | Examples                                      | HTTP |
| --------------- | --------------------------------------------- | ---- |
| ValidationError | missing/invalid param, enum failure           | 400  |
| GuardError      | path outside root, symlink traversal          | 403  |
| ParserError     | DuckDB ParserException (compile-time SQL bug) | 500  |
| ConstraintError | constraint on temp/append tables              | 409  |
| ResourceError   | OOM, temp space exceeded                      | 503  |
| NotFound        | route/version missing                         | 404  |
| AuthError       | login/session issues                          | 401  |
| ShareError      | invalid/expired/bound token                   | 403  |

* Log `error_category`, `request_id`, `route_id`, redacted message.
* UI shows short descriptive messages; details in logs.

---

## 21) Plugin Lifecycle & Extension Points

Registration helpers:

```python
register_postprocessor(name, func)
register_chart_renderer(type, func)
register_image_getter(name, func)
register_storage_adapter(name, class)
register_auth_adapter(name, class)
register_email_adapter(name, func)
```

* Discovery via optional Python entry points (`pyproject.toml`).
* Plugins run in-process; adhere to resource/time caps; no network by default.

---

## 22) CLI & Developer Experience

```
webbed_duck build            # compile *.sql.md → routes_build/*.py
webbed_duck validate         # parse & type-check route defs
webbed_duck serve --reload   # dev server with hot reload
webbed_duck explain          # print active config/adapters/features
webbed_duck run-incremental <route> [--start --end]  # iterate batches
```

**DX notes**

* Clear file:line diagnostics on compiler errors.
* `--dry-run` to render bound SQL for inspection (no execute).
* Route Manager page (dev): reload compiled routes, view schema, test params.

---

## 23) Testing Strategy & Coverage

**Unit**

* `core.duckrel`: Arrow conversion, Parquet/CSV writes.
* `core.config`: loading, env overrides, validation.
* `server.auth`: sessions, cookie flags by transport mode, domain allowlist, basic password path (if enabled).
* Preprocessors: coercions, range checks, path guards.
* Postprocessors & plugins: HTML_T/C snapshots, chart SVG, image getter fallback, registry demos (`tests/test_plugins.py`, `examples/plugin_registry_demo.py`).
* Share tokens: hashing, TTL, single-use, bindings.

**Integration**

* Compile sample routes → execute → overlay → render → cache.
* Virtual views: `limit/offset` with Arrow slices.
* Share link flow end-to-end (create/open/fail second use).
* Introspection endpoints & auto-forms.

**Security**

* Deny `../` traversal; deny symlinks outside root.
* No HTML injection/XSS: escape table cells; sanitize attributes.
* No plaintext passwords/tokens in logs.
* Rate-limit login/share creation; generic error strings.

**Performance**

* 100k rows to Parquet under target time; HTML truncation with banner.
* Memory bounded when paging via Arrow slices.

---

## 24) Performance Notes & Limits

* Push filters & aggregations into SQL; avoid Python loops.
* Use Arrow Table for any in-memory work; avoid DataFrame materialization.
* Charts: downsample/aggregate before render; cap series.
* Virtual viewers: fetch chunks of ~500–2000 rows; DOM virtualize ~300 visible rows.
* CSV append routes (if enabled later): queue writes; single writer; atomic appends.

---

## 25) Progress Trackers (Checklists & Mermaid Gantt)

### 25.1 Milestone Checklists

**MVP 0.1.x**

* [x] Compiler: `@meta/@params/@preprocess/@postprocess/@charts/@assets`
* [x] Per-request DuckDB exec + Arrow Table
* [x] Postprocessors: `html_t`, `parquet`, `csv`
* [x] Config loader + storage_root layout
* [x] Auth: `pseudo` + sessions (SQLite)
* [x] Share link (hash+TTL+UA/IP bind)
* [x] Introspection: `/routes`, `/routes/{id}/schema`
* [x] Tests: unit + integration basics
* [x] HTTP banner toggle (`ui.show_http_warning`)

**Beta 0.2.x**

* [x] `html_c` cards + `feed` virtual view
* [x] Arrow RPC slices for virtual viewers
* [x] Email shares (inline + attachments)
* [x] Image getter plugin (localize/cache assets)
* [x] Charts (SVG) + renderer registry
* [x] Plugin registry demos & regression tests outside core
* [x] Popularity analytics + folder indexes
* [x] Error taxonomy surfaced in UI
* [ ] Compiler: `@meta/@params/@preprocess/@postprocess/@charts/@assets`
* [ ] Per-request DuckDB exec + Arrow Table
* [ ] Postprocessors: `html_t`, `parquet`, `csv`
* [ ] Config loader + storage_root layout
* [ ] Auth: `pseudo` + sessions (SQLite)
* [ ] Share link (hash+TTL+UA/IP bind)
* [ ] Introspection: `/routes`, `/routes/{id}/schema`
* [x] Tests: unit + integration basics
* [ ] HTTP banner toggle (`ui.show_http_warning`)

**Beta 0.2.x**

* [ ] `html_c` cards + `feed` virtual view
* [ ] Arrow RPC slices for virtual viewers
* [ ] Email shares (inline + attachments)
* [x] Image getter plugin (localize/cache assets)
* [x] Charts (SVG) + renderer registry
* [ ] Popularity analytics + folder indexes
* [ ] Error taxonomy surfaced in UI

**GA 0.3.x**

* [x] Annotations/overrides (overlay store)
* [x] CSV append + generated forms
* [x] Incremental runner + checkpoints
* [x] Internal “local:” chaining API
* [x] External auth adapter interfaces (OIDC/Proxy)
* [x] Perf harness + full docs

### 25.2 Roadmap Gantt (Mermaid, **starts 01:45; pause 18:30–05:00**)

```mermaid
gantt
    title webbed_duck Roadmap - compressed to hours (start 2025-11-23 01:45; pause 18:30-05:00)
    dateFormat  YYYY-MM-DD HH:mm
    axisFormat  %m-%d %H:%M

    section MVP 0.1.x
    Compiler and Core Exec        :done, mvp1, 2025-11-23 01:45, 2025-11-23 05:45
    HTML_T plus Parquet/CSV       :done, mvp2, 2025-11-23 03:45, 2025-11-23 09:45
    Pseudo Auth and Sessions      :done, mvp3, 2025-11-23 06:00, 2025-11-23 11:00
    Link Sharing hashed           :done, mvp4, 2025-11-23 11:00, 2025-11-23 14:30
    Introspection Endpoints       :done, mvp5, 2025-11-23 14:30, 2025-11-23 16:30

    section Beta 0.2.x (pre-pause)
    Cards and Feed Virtual Views  :done, beta1, 2025-11-23 16:30, 2025-11-23 18:15

    section Pause
    Downtime 18:30-05:00          :pause1, 2025-11-23 18:30, 2025-11-24 05:00

    section Beta 0.2.x (resume)
    Arrow RPC Slices              :done, beta2, 2025-11-24 05:00, 2025-11-24 09:00
    Email Share and Attachments   :done, beta3, 2025-11-24 05:30, 2025-11-24 10:00
    Image Getter Plugin           :done, beta4, 2025-11-24 07:00, 2025-11-24 10:30
    Charts SVG and Registry       :done, beta5, 2025-11-24 08:00, 2025-11-24 11:00
    Analytics and Folder Index    :done, beta6, 2025-11-24 10:00, 2025-11-24 12:00
    Plugin Registry Demos & Tests :done, beta7, 2025-11-24 09:30, 2025-11-24 11:30

    section GA 0.3.x
    Annotations and Overrides     :done, ga1,  2025-11-24 12:00, 2025-11-24 18:00
    CSV Append and Forms          :done, ga2,  2025-11-24 13:30, 2025-11-24 19:30
    Incremental Runner            :done, ga3,  2025-11-24 14:00, 2025-11-24 20:00
    Local Route Chaining          :done, ga4,  2025-11-24 16:00, 2025-11-24 20:00
    External Auth Finalization    :done, ga5,  2025-11-24 19:30, 2025-11-24 23:30
    Perf Harness and Full Docs    :done, ga6,  2025-11-24 20:00, 2025-11-25 00:00
```

> No tasks are scheduled during **18:30 → 05:00**. Overlaps indicate staggered sub-tasks the agent can queue/alternate between while maintaining cadence outside the pause window.

---

## 26) Release, Versioning & Deprecations

* **Package**: SemVer; breaking API → major; features → minor; fixes → patch.
* **Routes**: version in `@meta.version`. Prod may keep only latest (N) active with a sunset window for N-1.
* **Migrations**: core never hardcodes storage DDL; adapters own their tables and migrations.
* **CHANGELOG.md**: concise entries, human & agent friendly.

---

## 27) Appendices (Config, Examples, Snippets)

### 27.1 Example `config.toml`

```toml
[server]
storage_root = "./storage"
theme = "system"

[transport]
mode = "insecure_http"
trusted_proxy_nets = ["127.0.0.1/32","10.0.0.0/8"]

[ui]
show_http_warning = true

[auth]
mode = "pseudo"
allowed_domains = ["company.local"]
session_ttl_minutes = 45
remember_me_days = 14
proxy_header_user = "x-remote-user"
proxy_header_email = "x-remote-email"
proxy_header_name = "x-remote-name"
external_adapter = "custom:auth.module.create"

[email]
adapter = "custom:examples.emailer.send_email"
from_address = "no-reply@company.local"
share_token_ttl_minutes = 90
bind_share_to_user_agent = true
bind_share_to_ip_prefix = true

[share]
max_total_size_mb = 15
zip_attachments = true
zip_passphrase_required = false
watermark = true

[cache]
ttl_hours = 24

[analytics]
enabled = true
weight_interactions = 3

[feature_flags]
annotations_enabled = true
comments_enabled = true
tasks_enabled = true
overrides_enabled = true

[assets]
default_image_getter = "static_fallback_getter"
```

### 27.2 Minimal emailer (tests/examples)

```python
# examples/emailer.py
from email.message import EmailMessage
import os, smtplib
from jinja2 import Environment, BaseLoader, select_autoescape

_JINJA = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
_TMPL = """<!doctype html><meta charset="utf-8"><h3>{{ title }}</h3><p>{{ message }}</p>{% if link %}<p><a href="{{ link }}">Open</a></p>{% endif %}"""

def render_html(title, message, link=None):
    return _JINJA.from_string(_TMPL).render(title=title, message=message, link=link)

def send_email(to_addrs, subject, html_body, text_body=None, attachments=None):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.getenv("SMTP_FROM","no-reply@company.local")
    msg["To"] = ", ".join(to_addrs)
    msg.set_content(text_body or subject)
    msg.add_alternative(html_body, subtype="html")
    for (filename, content) in (attachments or []):
        msg.add_attachment(content, maintype="application", subtype="octet-stream", filename=filename)
    host = os.getenv("SMTP_HOST","localhost"); port = int(os.getenv("SMTP_PORT","1025"))
    with smtplib.SMTP(host, port) as s: s.send_message(msg)
```

### 27.3 Image getter registration

```python
# plugins/assets.py
_REG = {}
def register_image_getter(name):
    def deco(fn):
        _REG[name] = fn; return fn
    return deco

@register_image_getter("static_fallback_getter")
def static_fallback(name: str, route_id: str) -> str:
    return f"/static/{name}"
```

### 27.4 Chart renderer stub

```python
# plugins/charts.py
_RENDER = {}
def register_chart_renderer(type_):
    def deco(fn):
        _RENDER[type_] = fn; return fn
    return deco
```

### 27.5 Local route chaining

```python
# core/local.py
def run_route(route_id: str, params: dict, format: str = "arrow"):
    # validate + execute in-process; reuse cache; return Arrow Table or artifact path
    ...
```

---

### Final reminders for contributors

* Prefer **efficient DuckDB SQL** over Python loops.
* Keep **preprocessors** minimal; push compute to SQL.
* Use **Arrow** for all in-memory data.
* Avoid new deps unless necessary; no network calls in core.
* Ensure modules are importable and tests green on every change.
* `webbed_duck` is **securable**—ship guardrails and clear, configurable behavior.
