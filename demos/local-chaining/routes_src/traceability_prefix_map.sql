WITH mappings AS (
  SELECT *
  FROM (
    VALUES
      ('PN', 'traceability_panel_events', 'traceability_panel_file_hints'),
      ('PN', 'traceability_module_events', 'traceability_module_file_hints'),
      ('MD', 'traceability_module_events', 'traceability_module_file_hints'),
      ('BD', 'traceability_panel_events', 'traceability_panel_file_hints')
  ) AS t(prefix, event_route, file_hint_route)
)
SELECT
  prefix,
  event_route AS table_route,
  file_hint_route
FROM mappings
WHERE prefix = UPPER($prefix)
ORDER BY table_route;
