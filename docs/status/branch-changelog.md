# Branch-level Changelog

## webbed_duck packaging hardening (work branch)

- Fix setuptools configuration so `pip install webbed-duck` installs the actual
  `webbed_duck` package hierarchy instead of leaking `core/`, `server/`, and
  `plugins/` modules at the root of site-packages.
- Add an optional `[test]` extra that pulls in `build` and a regression test
  that constructs a wheel and asserts the package layout is correct.
- Regenerate the sample `hello` route so its compiled artifact reflects the
  current compiler metadata (formats, postprocessors, directives).

## UI filters + Arrow RPC plumbing (work branch)

- Document how `[html_t]` / `[html_c]` `show_params` metadata drives parameter
  forms and demonstrate the workflow in the README.
- Update the HTML renderers to emit `wd-rpc-config` JSON, pagination summaries,
  and Arrow RPC download links while mirroring the RPC headers on responses.
- Expand the regression suite with tests that assert filter controls, hidden
  pagination inputs, and RPC metadata render for both table and card formats.
