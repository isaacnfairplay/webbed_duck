# Dynamic invariant select options

`webbed_duck` auto-populates HTML `<select>` controls for parameters that participate in `cache.invariant_filters`. When a route
does not specify `options` in TOML, the renderer behaves as if you had written `options = "...unique_values..."`—the sentinel that
expands to cached invariant tokens scoped to the current filter context.

## Quick reference

- Use the sentinel directly to make the behaviour explicit:
  ```toml
  [params]
  plant = { type = "str", description = "Manufacturing plant" }
  line = { type = "str", description = "Optional production line", options = "...unique_values..." }

  [cache]
  order_by = ["plant_day", "line"]
  invariant_filters = [
    { param = "line", column = "line" }
  ]
  ```
- Combine the sentinel with static values to append house-keeping choices or merged buckets without duplicating results:
  ```toml
  options = ["...unique_values...", { value = "Other", label = "Custom line" }]
  ```
- When other invariant filters are active, the renderer cross-references the cached index with the current result table so only
  relevant tokens remain in the dropdown.
- If a caller supplies a value that is not part of the cached index, the renderer still shows the submitted value to make the
  form state obvious.

## Why this matters

Dynamic select options keep HTML filters aligned with the cached dataset—especially for long-lived caches with invariant shards.
Route authors no longer need to maintain hand-curated option lists or write preprocessors to discover values. The sentinel works
for any invariant parameter (string, integer, or boolean) and can be layered with additional TOML metadata like `required = true`
or human-friendly descriptions.
