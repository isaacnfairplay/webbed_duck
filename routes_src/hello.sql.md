+++
id = "hello_world"
path = "/hello"
title = "Hello world"
description = "Return a greeting using DuckDB"
methods = ["GET"]

[params.name]
type = "str"
required = false
default = "world"
description = "Name to greet"

[html_c]
title_col = "greeting"
meta_cols = ["note", "created_at"]

[feed]
timestamp_col = "created_at"
title_col = "greeting"
summary_col = "note"

[[charts]]
id = "greeting_length"
type = "line"
y = "greeting_length"
+++

# Hello world

This route uses DuckDB string concatenation to produce a greeting.

```sql
SELECT
  'Hello, ' || {{name}} || '!' AS greeting,
  'Personalized greeting rendered by DuckDB' AS note,
  LENGTH('Hello, ' || {{name}} || '!')::INT AS greeting_length,
  CURRENT_TIMESTAMP AS created_at;
```
