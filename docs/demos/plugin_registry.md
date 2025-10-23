# Plugin Registry Demo

The `webbed_duck` plugin architecture can be exercised without booting the HTTP
server.  The demo below mirrors how downstream deployments can register custom
image getters and chart renderers from their own integration tests or helper
scripts.

## Demo script

The [`examples/plugin_registry_demo.py`](../../examples/plugin_registry_demo.py)
module installs a CDN-backed image getter and a simple "totalizer" chart
renderer.  Running the script resolves an image URL and renders the chart into a
small HTML card:

```bash
python examples/plugin_registry_demo.py
```

Example output:

```
Hero: https://cdn.intra.example/routes/overview/overview.png
Chart total -> <div class='chart-card'><h4>Total Value</h4><p>10.00</p></div>
```

The helpers in `render_demo` return plain data structures so downstream tests can
assert on chart HTML or resolved image URLs without coupling to the FastAPI
surface.

## Test coverage

The plugin registries are covered by `tests/test_plugins.py`, which now includes
checks for:

- Custom CDN image getters.
- Fallback resolution to the static asset getter.
- Custom chart renderers and renderer skipping for unknown types.
- Error propagation when renderers raise exceptions.
- Validation paths for the built-in line chart renderer (missing columns and
  non-numeric data).

These tests and the accompanying demo provide a bench of executable references
outside the main package source so teams can iterate on plugins confidently.
