WITH required_routes AS (
  SELECT
    prefix,
    table_route,
    file_hint_route
  FROM prefix_lookup
),
panel AS (
  SELECT
    'traceability_panel_events' AS table_route,
    barcode,
    event_time,
    station,
    status,
    work_center
  FROM panel_events
),
module AS (
  SELECT
    'traceability_module_events' AS table_route,
    barcode,
    event_time,
    station,
    status,
    work_center
  FROM module_events
),
all_events AS (
  SELECT * FROM panel
  UNION ALL
  SELECT * FROM module
),
file_hints AS (
  SELECT
    'traceability_panel_events' AS table_route,
    barcode_root,
    file_hint
  FROM panel_file_hints
  UNION ALL
  SELECT
    'traceability_module_events' AS table_route,
    barcode_root,
    file_hint
  FROM module_file_hints
),
combined AS (
  SELECT
    r.prefix AS barcode_prefix,
    r.table_route,
    r.file_hint_route,
    e.barcode,
    e.event_time,
    e.station,
    e.status,
    e.work_center,
    f.file_hint
  FROM required_routes AS r
  LEFT JOIN all_events AS e USING (table_route)
  LEFT JOIN file_hints AS f
    ON f.table_route = r.table_route
   AND f.barcode_root = REGEXP_EXTRACT(e.barcode, '^([^-]+-[^-]+)', 1)
)
SELECT
  barcode_prefix,
  table_route,
  file_hint_route,
  barcode,
  event_time,
  station,
  status,
  work_center,
  file_hint
FROM combined
WHERE barcode IS NOT NULL
ORDER BY event_time;
