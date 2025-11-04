WITH hints AS (
  SELECT *
  FROM (
    VALUES
      ('traceability_panel_events', 'PN-1001', '/lake/panels/2025/PN-1001.parquet'),
      ('traceability_panel_events', 'PN-2007', '/lake/panels/2025/PN-2007.parquet')
  ) AS t(table_route, barcode_root, file_hint)
)
SELECT
  table_route,
  barcode_root,
  file_hint
FROM hints
WHERE barcode_root = SPLIT_PART({{barcode}}, '-', 1)
   OR {{barcode}} LIKE barcode_root || '%'
ORDER BY file_hint;
