# webbed_duck

`webbed_duck` turns Markdown + SQL route files into HTTP endpoints powered by DuckDB.

This MVP (v0.1) delivers the essentials:

* A Markdown compiler that translates `*.sql.md` files into Python route manifests.
* A FastAPI-based server that executes DuckDB queries per-request and returns JSON payloads derived from Arrow tables.
* A command-line interface for compiling routes and running the development server.

See `routes_src/hello.sql.md` for an example route.

## Usage

Compile routes:

```bash
python -m webbed_duck.cli compile --source routes_src --build routes_build
```

Run the development server (requires the compiled routes):

```bash
python -m webbed_duck.cli serve --build routes_build --config config.toml
```

Visit `http://127.0.0.1:8000/hello?name=DuckDB` to exercise the sample route.
