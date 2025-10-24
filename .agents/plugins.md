# Plugin Creation Guidelines

These instructions apply when adding or modifying plug-ins under the `webbed_duck/plugins/` package or introducing plug-in registration helpers elsewhere in the repository. Follow them to ensure new extensions integrate cleanly with the compiler/runtime pipeline.

## 1. Core Principles

- **Registry-first design.** All plug-ins must register themselves via the appropriate registry helper (for example, `register_postprocessor`, `register_chart_renderer`, or `register_image_getter`) inside their module scope.
- **Pure functions.** Plug-in entry points should avoid global state. Rely on the request context that is passed into the plug-in and return serializable results (Arrow tables, strings, or dictionaries).
- **Graceful degradation.** Optional dependencies should be imported inside the callable or wrapped in helper functions that raise informative `ImportError` messages with remediation steps.
- **Documentation parity.** Every new plug-in needs a docstring summarizing its behavior and configuration knobs so route authors understand how to invoke it.

## 2. Module Layout & Naming

1. Place plug-ins inside `webbed_duck/plugins/` unless they are examples that belong under `examples/plugins/`.
2. Name files after the feature they extend (e.g., `html_postprocessors.py`, `charts_matplotlib.py`).
3. Expose a module-level `__all__` listing the public registration functions or plug-in callables to keep imports explicit.

## 3. Registration Patterns

Use the shared registry decorators from `webbed_duck/plugins/__init__.py` (or the specific submodule) to ensure the plug-in is discoverable at import time.

```python
from webbed_duck.plugins.postprocess import register_postprocessor

@register_postprocessor("html_table")
def html_table_postprocessor(request_ctx, arrow_table, *, template="table.html"):
    """Render an Arrow table to HTML using the default template."""
    ...
```

- Always import the registry helper at module top-level so registration occurs when the module is imported.
- Use keyword-only parameters for optional configuration to promote readability in route directives.
- Return values must match the expectations of the registry (e.g., strings for HTML, `dict` for JSON-like payloads, or tuples for multi-artifact responses).

## 4. Configuration & Routing

- Document any route directive syntax (e.g., `@postprocess html_table`) in inline comments or module docstrings.
- If the plug-in reads from `config.toml`, use `webbed_duck.core.config.get_config()` to avoid duplicating parsing logic.
- Prefer dependency injection through the request context over reading global state or environment variables.

## 5. Testing Expectations

- Add unit tests under `tests/plugins/` mirroring the module path (e.g., `test_postprocess_html.py`).
- Use deterministic fixtures—mock DuckDB outputs with Arrow tables created via `pyarrow.table` and avoid I/O where possible.
- Ensure tests cover registration (plug-in appears in the registry) and functional output (returned structure, MIME type hints, etc.).

## 6. Examples & Documentation

- Update `docs/plugins.md` or related HOWTOs with usage examples whenever a new plug-in type is introduced.
- Provide an example route under `routes_src/examples/` when the plug-in enables a new directive or data format.
- Include configuration snippets demonstrating how to toggle or reference the plug-in in `config.toml` when applicable.

Adhering to these guidelines keeps the plug-in surface predictable and allows downstream teams to audit, test, and extend the system confidently.
