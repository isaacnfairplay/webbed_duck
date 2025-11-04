# Embedding HTML in GitHub Markdown

This note captures the research behind rendering live HTML inside GitHub-hosted
Markdown, plus the patterns we use in the demos so contributors can keep
transcripts self-contained.

## GitHub Markdown capabilities

* GitHub allows inline HTML in Markdown files. The content is passed through the
  HTML sanitiser used by `github/markup`, so a predictable subset of tags is
  preserved. Structural elements such as `<div>`, `<span>`, `<header>`, `<table>`,
  and semantic inline tags render as expected.
* Potentially dangerous markup is stripped. `<script>` blocks (including JSON
  script tags), `<style>` content, most `on*` event handlers, and unsupported
  elements such as `<iframe>` or `<form>` are removed. This keeps previews safe
  but means dynamic behaviour needs to be demonstrated through static markup or
  screenshots.
* Attributes are filtered as well. Safe attributes like `class`, `id`, `data-*`,
  and ARIA roles survive sanitisation, but anything that could execute code is
  discarded.

## Recommended pattern for demos

To keep demo transcripts readable while preserving the raw responses:

1. **Include the response body as a fenced code block** using ` ```html ` for
   syntax highlighting. Wrap the block in a `<details>` disclosure element so
   the giant response does not dominate the page.
2. **Embed a sanitised preview directly in the Markdown** immediately after the
   code block. We strip `<script>` and `<style>` nodes and render the remaining
   body markup inside a `<div class="demo-preview">` container. This mirrors the
   approach already used by the parameter form and overrides demos.
3. **Keep the HTML next to the transcript**. If an HTML or JS asset is stored as
   a separate artifact for reuse, it must also be embedded inline so readers do
   not need to leave GitHub to inspect it.
4. **Document the source of the preview** via a `data-source` attribute (for
   example the HTTP request line). It is safe to rely on HTML entity encoding for
   query strings because GitHub renders escaped attributes correctly.

## Fallback plan

If the sanitised preview removes critical pieces (for example a canvas that
relies on a script tag), capture the rendered page as an image and include the
snapshot in the transcript alongside the code block. Screenshots keep the demo
self-contained even when GitHub strips interactivity.

## Implementation references

* `demos/route-authoring/generate_demo.py` now emits both the `<details>` code
  block and the inline preview for HTML responses, matching the guidance above.
* Existing demos that already used `demo-preview` containers (parameter forms,
  overrides) continue to work without changes because they follow the same
  pattern.
