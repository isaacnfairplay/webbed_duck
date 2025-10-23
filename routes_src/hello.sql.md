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
+++

# Hello world

This route uses DuckDB string concatenation to produce a greeting.

```sql
SELECT 'Hello, ' || {{name}} || '!' AS greeting;
```
