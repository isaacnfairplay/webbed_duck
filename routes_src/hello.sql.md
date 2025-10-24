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
ui_control = "input"
ui_label = "Name"
ui_placeholder = "Your teammate"
ui_help = "Type a name and press Apply to refresh the greeting"

[cache]
ttl_hours = 12
order_by = ["created_at"]

[html_t]
show_params = ["name"]

[html_c]
title_col = "greeting"
meta_cols = ["note", "created_at"]
show_params = ["name"]

[feed]
timestamp_col = "created_at"
title_col = "greeting"
summary_col = "note"

[overrides]
key_columns = ["greeting"]
allowed = ["note"]

[append]
columns = ["greeting", "note", "created_at"]
destination = "hello_appends.csv"

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
