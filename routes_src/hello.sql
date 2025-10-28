SELECT
  'Hello, ' || {{name}} || '!' AS greeting,
  'Personalized greeting rendered by DuckDB' AS note,
  LENGTH('Hello, ' || {{name}} || '!')::INT AS greeting_length,
  CURRENT_TIMESTAMP AS created_at;
