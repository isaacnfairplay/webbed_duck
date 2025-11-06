# Webbed Duck 1.0 Rewrite Proposal

## 1. Vision & guiding principles
- Preserve the existing feature surface while **drastically simplifying** the runtime and compiler layers.
- Apply SOLID principles explicitly:
  - **Single responsibility** modules for route compilation, execution, caching, UI rendering, and plugin wiring.
  - **Open/closed** execution and rendering paths via Strategy objects.
  - **Liskov**-compliant abstractions for DuckDB connections and cache stores so drop-in replacements remain safe.
  - **Interface segregation** between authoring (compiler) and serving (runtime) concerns.
  - **Dependency inversion** through typed service interfaces bound during app start-up.
- Lean on proven design patterns (Factory, Strategy, Builder, Template Method) to keep cross-cutting concerns predictable.
- Remove implicit behaviour; everything route authors can rely on is documented and enforced through typed configuration.
- Prefer declarative configuration (TOML/JSON) only for static data. Executable routes live in Python modules with explicit entry points.

## 2. Layered architecture
```
webbed_duck/
├── core/
│   ├── domain/          # Route entities, parameters, filters, chart models
│   ├── services/        # Compilers, executors, planners, cache orchestrators
│   ├── plugins/         # Base interfaces for preprocess, charts, assets, UI, auth
│   └── utils/           # Shared utilities (path, keyring, Arrow helpers)
├── infrastructure/
│   ├── duckdb/          # Connection factory, migrations, extension installers
│   ├── cache/           # Disk/Arrow cache stores + adaptive page sizing heuristics
│   ├── file_watcher/    # Incremental compiler (watch folders)
│   ├── secrets/         # Keyring + secure storage adapters
│   └── http/            # FastAPI integration, middleware, auth providers
├── runtime/
│   ├── app.py           # `create_app(config)` returning FastAPI application
│   ├── routes_loader.py # Loads compiled Python routes into runtime registry
│   └── local_runner.py  # Local execution API & chaining helpers
├── compiler/
│   ├── parser.py        # TOML + folder config reader
│   ├── builder.py       # Builds RouteDefinition objects using Builder pattern
│   ├── python_gen.py    # Emits compiled Python modules
│   └── artifacts/       # Shared templates for generated files
├── ui/
│   ├── renderers/       # HTML table, feed, card, dashboard composers
│   └── charts/          # Chart backend adapters (Chart.js, Matplotlib, etc.)
└── cli/
    └── __main__.py      # Optional helper for compile/watch; not required to serve
```

## 3. Route definition model
- Every compiled route becomes a Python module under `routes_build/<folder>/route_<name>.py`.
- Modules export a `Route` object implementing `Callable[[RouteContext], RouteResult]`.
- Structure (Template Method pattern):
  ```python
  class SalesByRegion(RouteBase):
      metadata = RouteMetadata(
          id="sales/by_region",
          formats=[Format.ARROW, Format.HTML_TABLE, Format.CHART],
          filters=[InvariantFilter(...), NonInvariantFilter(...)],
          charts=[ChartSpec("bar", dataset="sales")],
          constants=RouteConstants(...),
      )

      def preprocess(self, ctx):
          ctx.run_sql_file("./sql/init_extensions.sql", mode="execute")

      def query(self, ctx):
          params = ctx.params.bind(schema=self.metadata.param_schema)
          return ctx.duckdb.query_file("./sql/main.sql", params=params)

      def postprocess(self, ctx, table):
          return ctx.render_html_table(table)
  ```
- Route modules may import helpers from sibling modules. Calling another route uses a dedicated helper `ctx.run_route("other/id", params)` which inlines the compiled callable during generation to avoid dynamic imports.
- Declarative TOML files become optional: if present they hold metadata only. Raw metadata can be placed in JSON/TOML, but compiled modules are canonical.

## 4. Configuration hierarchy
- `config.toml` (server-wide): server constants, secrets (keyring lookups), cache defaults, DuckDB location, chart backend priority, feature flags.
- **Folder-level `folder.toml`**: shared metadata for all routes beneath (default filters, shared UI assets, default preprocess scripts, dashboard fragments, plugin selections).
- Route-level metadata defined either via `route.toml` or inline in the Python module.
- Constants precedence: server > folder > route (route may shadow). Secrets defined as `[[secrets]]` entries referencing keyring service + key.
- Preprocess blocks in TOML reference SQL scripts with execution modes per statement (`run_mode = "query" | "execute"`). Compiler enforces final statement in query mode when response requires result set.

## 5. Execution pipeline
1. **Configuration resolution**: merge server/folder/route metadata into a `RouteDefinition` object using Builder pattern.
2. **Preprocess stage**: Template Method ensures `preprocess()` runs before `query()`. Support multiple SQL files, extension installers, and Python callables (via plugin registry) with explicit return contracts.
3. **Parameter binding**:
   - Typed schema defined via `ParamSchema` (Strategy pattern for coercion).
   - All non-constant inputs validated; string interpolation only allowed when backed by enumerated whitelist or sanitized via safe identifier wrapper.
   - Date/time helpers convert to DuckDB-compatible formats; server provides reusable converters (ISO, start/end-of-day, custom strftime) configured per parameter.
4. **Route chaining**: `ctx.route_client` executes other routes synchronously using isolated DuckDB connections but shared cache namespace. Compiler expands inline call graph to remove runtime import coupling.
5. **Execution**: `DuckDBExecutor` ensures per-route connection, optional extension install, query vs execute mode enforcement.
6. **Postprocess**: Format-specific Strategy objects (ArrowResponse, HtmlTableResponse, HtmlFeedResponse, HtmlCardResponse, ChartResponse). Dashboard composer planned as aggregator of multiple `HtmlComponent` instances with shared filter context.
7. **Caching**:
   - `CachePlan` decides caching policy using metadata and heuristics.
   - Adaptive page size: start with default (e.g., 5k rows). Collect metrics (execution time, result size) to update `PageSizeModel` stored per route version. Provide offline CLI to recompute heuristics if desired.
   - Cache directories computed per route, overrideable via server/folder config.

## 6. Plugin system simplification
- Single registration decorator per plugin type:
  ```python
  @chart_renderer.register("chartjs")
  def render_chartjs(dataset: ChartDataset, options: ChartOptions) -> HtmlComponent:
      ...
  ```
- Plugins discoverable via entry points **and** explicit imports. Registration occurs during app bootstrap, not via dynamic module loading.
- Supported plugin categories: preprocess callables, chart renderers, HTML widgets, asset providers, auth adapters.
- Plugin interfaces documented via Protocols; base classes offer sensible defaults.
- Route authors reference plugins by key; compiler validates availability during build.

## 7. HTTP & application hosting
- Provide `webbed_duck.runtime.app.create_app(config_path: str | Config)` returning FastAPI application; users can mount it in any ASGI server.
- CLI reduced to helpers (`webbed-duck compile`, `webbed-duck watch`, `webbed-duck dev`) but serving is done via `uvicorn webbed_duck.runtime.app:create_app --factory` or embedding into larger apps.
- File watcher rebuilds affected routes and reloads FastAPI router via hot-swap service (Observer pattern).

## 8. Front-end & UI features
- Three built-in HTML renderers: Table, Feed, Card. Each exposes consistent filter UI automatically using metadata.
- Chart backend Strategy: Chart.js (default) and Matplotlib parity ensured by shared `ChartDataset` specification. Add stubs for future backends (Plotly, Vega-Lite).
- Dashboard composer (future): defined via folder-level config referencing route components with shared filter definitions.
- UI assets pluggable per folder/route via folder config; HTML/JS snippets allowed through explicit manifest lists.

## 9. Local route runner & chaining
- `LocalRouteRunner` exposes synchronous API for local jobs and chained routes.
- Supports Arrow, DuckDB relation, JSON export, CSV/Parquet writing.
- Path-based chaining (e.g., `local:../folder/route`) resolved during compilation; relative paths validated.
- Arrow file/stream exchange available for pipeline chaining.

## 10. Caching & storage clarity
- Cache configuration expressed via `CacheConfig` objects: storage path, TTL, page size bounds, partitioning strategy (invariant/non-invariant filters), and materialization format (Arrow IPC, Parquet).
- Clear invariants documented: invariant filters must declare canonical sort order; non-invariant filters are applied on cached shards as feasible.
- Provide introspection endpoint `/__cache__/<route>` exposing metrics, current page size, hit/miss stats.

## 11. Security & secrets
- Secrets loaded via Keyring adapters; injection allowed only through named parameters.
- SQL template engine limited to `{param}` substitution with strict typing; no arbitrary code execution.
- Preprocess scripts allowed to install extensions using whitelisted commands defined in config.

## 12. Parameter & filter ergonomics
- Built-in validators for numeric ranges, enum sets, dates (with format conversion), and safe identifiers.
- Filter definitions describe invariance, UI control type, default value, and transformation steps.
- Automatic dropdown population for invariant filters continues; non-invariant filters render free-form controls with server-side validation.

## 13. Dashboard & extensibility roadmap
- Phase 1: single-route HTML components with pluggable charts/cards.
- Phase 2: dashboard layout defined in folder config, referencing multiple routes, reusing shared filter context managed by runtime.
- Provide plugin interface for custom layout engines while maintaining consistent parameter binding.

## 14. Migration strategy
- New compiler generates Python modules from existing TOML+SQL definitions (preserving behaviour) but encourages manual curation.
- Legacy dictionary-based compiled routes deprecated; compatibility shim loads them but warns during startup.
- Provide tooling to convert JSON/TOML compiled artifacts into new class-based modules.

## 15. Testing expectations
- Unit tests per module; integration tests for compiler, executor, plugin loading, caching heuristics, UI renderers, and dashboard composition.
- Golden-file tests for generated Python modules and HTML outputs.
- Smoke tests ensuring Chart.js and Matplotlib renderers produce equivalent semantics.

