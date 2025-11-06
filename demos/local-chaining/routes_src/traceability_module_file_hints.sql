WITH hints AS (
  SELECT *
  FROM (
    VALUES
      ('traceability_module_events', 'PN-1001', '/lake/modules/2025/PN-1001-modules.parquet'),
      ('traceability_module_events', 'MD-5005', '/lake/modules/2025/MD-5005.parquet')
  ) AS t(table_route, barcode_root, file_hint)
)
SELECT
  table_route,
  barcode_root,
  file_hint
FROM hints
WHERE barcode_root = SPLIT_PART($barcode, '-', 1)
   OR $barcode LIKE barcode_root || '%'
ORDER BY file_hint;
