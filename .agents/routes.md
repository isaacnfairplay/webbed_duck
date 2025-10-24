# Route Template Generation Guidelines

These instructions are for agents that will be generating new Markdown+SQL route templates for the `webbed_duck` project. Follow them whenever you work with files under `routes_src/` or produce example route content for documentation and tests.

## Core Expectations

1. **Keep templates minimal yet functional.** Each template must:
   - Declare `@meta` information with at least a `title` and `description` that summarize the route.
   - Include an explicit `@params` block (even if empty) to document accepted inputs.
   - Provide at least one runnable SQL statement that returns a predictable schema, ideally referencing DuckDB sample data sources (e.g., `read_csv_auto`, `read_parquet`, or in-memory CTEs).
2. **Use deterministic sample data.** Prefer CTEs with hard-coded rows when the template demonstrates logic rather than data loading. This keeps tests stable and ensures compilation without external files.
3. **Demonstrate best practices.** Highlight secure parameterization, limited result sets (`LIMIT 100`), and human-readable column aliases.

## Formatting Rules

- Start each section with a Markdown heading (`#`, `##`, etc.) before directives to improve readability in rendered docs.
- Leave one blank line between directive blocks (`@meta`, `@params`, `@preprocess`, `@sql`, `@postprocess`).
- Align YAML-style lists and dictionaries with two-space indentation.
- Use fenced code blocks for extended SQL examples inside Markdown explanations, but keep the executable SQL inside `@sql` blocks.

## SQL Conventions

- Uppercase SQL keywords; lowercase identifiers.
- Alias complex expressions (e.g., `COUNT(*) AS row_count`).
- When demonstrating parameter usage, show both default values and validation comments inside the `@params` block.

## Testing Hooks

- If the template needs a preprocess step, document the expected Python callable path and summarize its behavior.
- Mention relevant pytest module names when applicable so test authors know where to add coverage.

## Template Skeleton

Use the following scaffold as a starting point. Replace bracketed placeholders with concrete values and adapt the Markdown narrative to the route's purpose.

```markdown
# <Route Title>

Intro sentence or two explaining the audience and the insight this route provides.

@meta
title: <Route Title>
description: <Concise description of what the SQL returns>
tags:
  - demo
  - <optional-domain-tag>

@params
filters:
  type: struct
  required: false
  fields:
    country:
      type: text
      required: false
      default: 'USA'
      description: Limit results to a specific country.
    limit:
      type: integer
      required: false
      default: 100
      description: Row cap to avoid large payloads.

## Methodology

Explain data sourcing, assumptions, and why defaults are safe. Mention tests that rely on the template if applicable.

@sql
WITH source AS (
    SELECT *
    FROM read_csv_auto('data/sample_sales.csv')
),
filtered AS (
    SELECT *
    FROM source
    WHERE country = coalesce({{ filters.country }}, country)
    LIMIT {{ filters.limit }}
)
SELECT
    order_date,
    customer_name,
    total_amount AS order_total
FROM filtered
ORDER BY order_date DESC
LIMIT {{ filters.limit }};

@postprocess html_t
template: charts/table_with_summary.html
```

## Review Checklist for Agents

Before finalizing a template:

- [ ] `@meta` block includes `title` and `description`.
- [ ] `@params` block documents each parameter's `type`, `required`, and `default` when applicable.
- [ ] SQL runs without external dependencies.
- [ ] Template comments explain its purpose in one or two sentences.
- [ ] Added tests (if any) reference deterministic data sources.

The scaffold above is illustrative—treat it as a template to adapt rather than a rigid sequence. Following these guidelines ensures generated templates remain consistent, secure, and easy for maintainers to understand.
