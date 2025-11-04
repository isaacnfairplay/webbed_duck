WITH events AS (
  SELECT *
  FROM (
    VALUES
      ('PN-1001', TIMESTAMP '2025-01-15 08:30:00', 'Laser Mark', 'Serial engraved', 'Line A'),
      ('PN-1001', TIMESTAMP '2025-01-15 09:00:00', 'AOI', 'Inspection passed', 'Line A'),
      ('PN-1001', TIMESTAMP '2025-01-15 11:20:00', 'Wave Solder', 'Solder joints complete', 'Line A'),
      ('PN-2007', TIMESTAMP '2025-01-16 07:45:00', 'Laser Mark', 'Serial engraved', 'Line B')
  ) AS t(barcode, event_time, station, status, work_center)
)
SELECT
  barcode,
  event_time,
  station,
  status,
  work_center,
  'traceability_panel_events' AS source_route
FROM events
WHERE barcode = {{barcode}} OR barcode LIKE {{barcode}} || '%'
ORDER BY event_time;
