# Module-based preprocess demo

This demo highlights the new `callable_module` + `callable_name` contract for preprocessors.

## What it shows

* The route metadata references a packaged helper via:

  ```toml
  [[preprocess]]
  callable_module = "webbed_duck.demos.preprocess_plugins"
  callable_name = "append_suffix"
  source = "input"
  target = "processed"
  suffix = "-module"
  ```

* `webbed_duck compile --source demos/preprocess-module/routes_src --build demos/preprocess-module/routes_build`
  resolves the module at build time. A missing module or callable stops the build with a descriptive error.
* Serving from the generated build demonstrates that the enriched parameter (`processed`) is available during SQL execution.

## Quick run

```bash
uv run webbed-duck compile --source demos/preprocess-module/routes_src --build demos/preprocess-module/routes_build
uv run webbed-duck serve --build demos/preprocess-module/routes_build --no-watch --no-auto-compile --host 127.0.0.1 --port 8765
# In another shell
curl "http://127.0.0.1:8765/demos/preprocess/module?input=feather"
```

The response echoes `feather` as `input_value` and `feather-module` as `processed_value`, proving that the module-backed
preprocessor ran before DuckDB executed the SQL.
