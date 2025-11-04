WITH events AS (
  SELECT *
  FROM (
    VALUES
      ('PN-1001-M1', TIMESTAMP '2025-01-15 12:05:00', 'Module Assembly', 'Module M1 married to panel', 'Cell 3'),
      ('PN-1001-M2', TIMESTAMP '2025-01-15 12:20:00', 'Module Assembly', 'Module M2 married to panel', 'Cell 3'),
      ('MD-5005', TIMESTAMP '2025-01-14 18:15:00', 'Module Test', 'Functional test passed', 'Test Lab')
  ) AS t(barcode, event_time, station, status, work_center)
)
SELECT
  barcode,
  event_time,
  station,
  status,
  work_center,
  'traceability_module_events' AS source_route
FROM events
WHERE barcode = {{barcode}} OR barcode LIKE {{barcode}} || '%'
ORDER BY event_time;
