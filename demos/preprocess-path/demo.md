# Filesystem path preprocess demo

This demo exercises the `callable_path` + `callable_name` contract by pointing a route at a Python file that lives beside the
demo content.

## What it shows

* The route metadata references the helper via:

  ```toml
  [[preprocess]]
  callable_path = "demos/preprocess-path/plugins/path_preprocessors.py"
  callable_name = "append_suffix_from_path"
  source = "input"
  target = "processed"
  suffix = "-path"
  source_file = "demos/preprocess-path/plugins/path_preprocessors.py"
  ```

* `webbed_duck compile --source demos/preprocess-path/routes_src --build demos/preprocess-path/routes_build`
  validates that the Python file exists and that `append_suffix_from_path` is callable. A missing file, missing `__init__.py`, or
  misspelled function name fails compilation with a targeted error.
* The preprocessor mirrors the input string into `processed` while recording the Python file path so you can see which script
  executed.

## Quick run

```bash
uv run webbed-duck compile --source demos/preprocess-path/routes_src --build demos/preprocess-path/routes_build
uv run webbed-duck serve --build demos/preprocess-path/routes_build --no-watch --no-auto-compile --host 127.0.0.1 --port 8765
# In another shell
curl "http://127.0.0.1:8765/demos/preprocess/path?input=teal"
```

The JSON response confirms the suffix (`teal-path`) and echoes the `preprocessor_source` file, proving that the reference loaded
from disk successfully.
