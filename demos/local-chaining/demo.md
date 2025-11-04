<!-- AUTO-GENERATED: Run `python generate_demo.py` to refresh. -->
# Local Route Chaining Demo

Generated on 2025-11-04T15:49:37.903620+00:00 UTC.

## Feature & Auth Toggles

These toggles were applied during the run and restored afterwards:

- **auth.mode**: "none" → "pseudo"
- **feature_flags.overrides_enabled**: false → true

## Command Transcript

### 1. Compile routes

**Command**

```python
compile_routes(SRC_DIR, BUILD_DIR)
```

**Response JSON**

```json
{
  "compiled_route_ids": [
    "traceability_barcode_summary",
    "traceability_module_events",
    "traceability_module_file_hints",
    "traceability_panel_events",
    "traceability_panel_file_hints",
    "traceability_prefix_map"
  ]
}
```

### 2. Prefix mapping lookup

**Command**

```python
runner.run(route_id="traceability_prefix_map", params={"prefix": "PN"}, format="records")
```

**Response JSON**

```json
{
  "rows": [
    {
      "file_hint_route": "traceability_module_file_hints",
      "prefix": "PN",
      "table_route": "traceability_module_events"
    },
    {
      "file_hint_route": "traceability_panel_file_hints",
      "prefix": "PN",
      "table_route": "traceability_panel_events"
    }
  ]
}
```

**Notes**

- used_cache: True
- cache_hit: False
- total_rows: 2
- applied_offset: 0
- applied_limit: None
- call_sequence: [
  {
    "route_id": "traceability_prefix_map",
    "used_cache": true,
    "cache_hit": false,
    "total_rows": 2,
    "applied_offset": 0,
    "applied_limit": null
  }
]

### 3. Panel events lookup

**Command**

```python
runner.run(route_id="traceability_panel_events", params={"barcode": "PN-1001"}, format="records")
```

**Response JSON**

```json
{
  "rows": [
    {
      "barcode": "PN-1001",
      "event_time": "2025-01-15T08:30:00",
      "source_route": "traceability_panel_events",
      "station": "Laser Mark",
      "status": "Serial engraved",
      "work_center": "Line A"
    },
    {
      "barcode": "PN-1001",
      "event_time": "2025-01-15T09:00:00",
      "source_route": "traceability_panel_events",
      "station": "AOI",
      "status": "Inspection passed",
      "work_center": "Line A"
    },
    {
      "barcode": "PN-1001",
      "event_time": "2025-01-15T11:20:00",
      "source_route": "traceability_panel_events",
      "station": "Wave Solder",
      "status": "Solder joints complete",
      "work_center": "Line A"
    }
  ]
}
```

**Notes**

- used_cache: True
- cache_hit: False
- total_rows: 3
- applied_offset: 0
- applied_limit: None
- call_sequence: [
  {
    "route_id": "traceability_panel_events",
    "used_cache": true,
    "cache_hit": false,
    "total_rows": 3,
    "applied_offset": 0,
    "applied_limit": null
  }
]

### 4. Traceability summary first execution

**Command**

```python
runner.run(route_id="traceability_barcode_summary", params={"barcode": "PN-1001"}, format="records")
```

**Response JSON**

```json
{
  "rows": [
    {
      "barcode": "PN-1001",
      "barcode_prefix": "PN",
      "event_time": "2025-01-15T08:30:00",
      "file_hint": "/lake/panels/2025/PN-1001.parquet",
      "file_hint_route": "traceability_panel_file_hints",
      "station": "Laser Mark",
      "status": "Serial engraved",
      "table_route": "traceability_panel_events",
      "work_center": "Line A"
    },
    {
      "barcode": "PN-1001",
      "barcode_prefix": "PN",
      "event_time": "2025-01-15T09:00:00",
      "file_hint": "/lake/panels/2025/PN-1001.parquet",
      "file_hint_route": "traceability_panel_file_hints",
      "station": "AOI",
      "status": "Inspection passed",
      "table_route": "traceability_panel_events",
      "work_center": "Line A"
    },
    {
      "barcode": "PN-1001",
      "barcode_prefix": "PN",
      "event_time": "2025-01-15T11:20:00",
      "file_hint": "/lake/panels/2025/PN-1001.parquet",
      "file_hint_route": "traceability_panel_file_hints",
      "station": "Wave Solder",
      "status": "Solder joints complete",
      "table_route": "traceability_panel_events",
      "work_center": "Line A"
    },
    {
      "barcode": "PN-1001-M1",
      "barcode_prefix": "PN",
      "event_time": "2025-01-15T12:05:00",
      "file_hint": "/lake/modules/2025/PN-1001-modules.parquet",
      "file_hint_route": "traceability_module_file_hints",
      "station": "Module Assembly",
      "status": "Module M1 married to panel",
      "table_route": "traceability_module_events",
      "work_center": "Cell 3"
    },
    {
      "barcode": "PN-1001-M2",
      "barcode_prefix": "PN",
      "event_time": "2025-01-15T12:20:00",
      "file_hint": "/lake/modules/2025/PN-1001-modules.parquet",
      "file_hint_route": "traceability_module_file_hints",
      "station": "Module Assembly",
      "status": "Module M2 married to panel",
      "table_route": "traceability_module_events",
      "work_center": "Cell 3"
    }
  ]
}
```

**Notes**

- used_cache: True
- cache_hit: False
- total_rows: 5
- applied_offset: 0
- applied_limit: None
- call_sequence: [
  {
    "route_id": "traceability_prefix_map",
    "used_cache": true,
    "cache_hit": true,
    "total_rows": 2,
    "applied_offset": 0,
    "applied_limit": null
  },
  {
    "route_id": "traceability_panel_events",
    "used_cache": true,
    "cache_hit": true,
    "total_rows": 3,
    "applied_offset": 0,
    "applied_limit": null
  },
  {
    "route_id": "traceability_module_events",
    "used_cache": true,
    "cache_hit": false,
    "total_rows": 2,
    "applied_offset": 0,
    "applied_limit": null
  },
  {
    "route_id": "traceability_panel_file_hints",
    "used_cache": true,
    "cache_hit": false,
    "total_rows": 1,
    "applied_offset": 0,
    "applied_limit": null
  },
  {
    "route_id": "traceability_module_file_hints",
    "used_cache": true,
    "cache_hit": false,
    "total_rows": 1,
    "applied_offset": 0,
    "applied_limit": null
  },
  {
    "route_id": "traceability_barcode_summary",
    "used_cache": true,
    "cache_hit": false,
    "total_rows": 5,
    "applied_offset": 0,
    "applied_limit": null
  }
]
- dependencies: [
  {
    "parent": "traceability_barcode_summary",
    "alias": "prefix_lookup",
    "target": "traceability_prefix_map"
  },
  {
    "parent": "traceability_barcode_summary",
    "alias": "panel_events",
    "target": "traceability_panel_events"
  },
  {
    "parent": "traceability_barcode_summary",
    "alias": "module_events",
    "target": "traceability_module_events"
  },
  {
    "parent": "traceability_barcode_summary",
    "alias": "panel_file_hints",
    "target": "traceability_panel_file_hints"
  },
  {
    "parent": "traceability_barcode_summary",
    "alias": "module_file_hints",
    "target": "traceability_module_file_hints"
  }
]

### 5. Traceability summary cached execution

**Command**

```python
runner.run(route_id="traceability_barcode_summary", params={"barcode": "PN-1001"}, format="records")
```

**Response JSON**

```json
{
  "rows": [
    {
      "barcode": "PN-1001",
      "barcode_prefix": "PN",
      "event_time": "2025-01-15T08:30:00",
      "file_hint": "/lake/panels/2025/PN-1001.parquet",
      "file_hint_route": "traceability_panel_file_hints",
      "station": "Laser Mark",
      "status": "Serial engraved",
      "table_route": "traceability_panel_events",
      "work_center": "Line A"
    },
    {
      "barcode": "PN-1001",
      "barcode_prefix": "PN",
      "event_time": "2025-01-15T09:00:00",
      "file_hint": "/lake/panels/2025/PN-1001.parquet",
      "file_hint_route": "traceability_panel_file_hints",
      "station": "AOI",
      "status": "Inspection passed",
      "table_route": "traceability_panel_events",
      "work_center": "Line A"
    },
    {
      "barcode": "PN-1001",
      "barcode_prefix": "PN",
      "event_time": "2025-01-15T11:20:00",
      "file_hint": "/lake/panels/2025/PN-1001.parquet",
      "file_hint_route": "traceability_panel_file_hints",
      "station": "Wave Solder",
      "status": "Solder joints complete",
      "table_route": "traceability_panel_events",
      "work_center": "Line A"
    },
    {
      "barcode": "PN-1001-M1",
      "barcode_prefix": "PN",
      "event_time": "2025-01-15T12:05:00",
      "file_hint": "/lake/modules/2025/PN-1001-modules.parquet",
      "file_hint_route": "traceability_module_file_hints",
      "station": "Module Assembly",
      "status": "Module M1 married to panel",
      "table_route": "traceability_module_events",
      "work_center": "Cell 3"
    },
    {
      "barcode": "PN-1001-M2",
      "barcode_prefix": "PN",
      "event_time": "2025-01-15T12:20:00",
      "file_hint": "/lake/modules/2025/PN-1001-modules.parquet",
      "file_hint_route": "traceability_module_file_hints",
      "station": "Module Assembly",
      "status": "Module M2 married to panel",
      "table_route": "traceability_module_events",
      "work_center": "Cell 3"
    }
  ]
}
```

**Notes**

- used_cache: True
- cache_hit: True
- total_rows: 5
- applied_offset: 0
- applied_limit: None
- call_sequence: [
  {
    "route_id": "traceability_barcode_summary",
    "used_cache": true,
    "cache_hit": true,
    "total_rows": 5,
    "applied_offset": 0,
    "applied_limit": null
  }
]

### 6. Traceability summary for module barcode

**Command**

```python
runner.run(route_id="traceability_barcode_summary", params={"barcode": "MD-5005"}, format="records")
```

**Response JSON**

```json
{
  "rows": [
    {
      "barcode": "MD-5005",
      "barcode_prefix": "MD",
      "event_time": "2025-01-14T18:15:00",
      "file_hint": "/lake/modules/2025/MD-5005.parquet",
      "file_hint_route": "traceability_module_file_hints",
      "station": "Module Test",
      "status": "Functional test passed",
      "table_route": "traceability_module_events",
      "work_center": "Test Lab"
    }
  ]
}
```

**Notes**

- used_cache: True
- cache_hit: False
- total_rows: 1
- applied_offset: 0
- applied_limit: None
- call_sequence: [
  {
    "route_id": "traceability_prefix_map",
    "used_cache": true,
    "cache_hit": false,
    "total_rows": 1,
    "applied_offset": 0,
    "applied_limit": null
  },
  {
    "route_id": "traceability_panel_events",
    "used_cache": true,
    "cache_hit": false,
    "total_rows": 0,
    "applied_offset": 0,
    "applied_limit": null
  },
  {
    "route_id": "traceability_module_events",
    "used_cache": true,
    "cache_hit": false,
    "total_rows": 1,
    "applied_offset": 0,
    "applied_limit": null
  },
  {
    "route_id": "traceability_panel_file_hints",
    "used_cache": true,
    "cache_hit": false,
    "total_rows": 0,
    "applied_offset": 0,
    "applied_limit": null
  },
  {
    "route_id": "traceability_module_file_hints",
    "used_cache": true,
    "cache_hit": false,
    "total_rows": 1,
    "applied_offset": 0,
    "applied_limit": null
  },
  {
    "route_id": "traceability_barcode_summary",
    "used_cache": true,
    "cache_hit": false,
    "total_rows": 1,
    "applied_offset": 0,
    "applied_limit": null
  }
]
- dependencies: [
  {
    "parent": "traceability_barcode_summary",
    "alias": "prefix_lookup",
    "target": "traceability_prefix_map"
  },
  {
    "parent": "traceability_barcode_summary",
    "alias": "panel_events",
    "target": "traceability_panel_events"
  },
  {
    "parent": "traceability_barcode_summary",
    "alias": "module_events",
    "target": "traceability_module_events"
  },
  {
    "parent": "traceability_barcode_summary",
    "alias": "panel_file_hints",
    "target": "traceability_panel_file_hints"
  },
  {
    "parent": "traceability_barcode_summary",
    "alias": "module_file_hints",
    "target": "traceability_module_file_hints"
  }
]

### 7. run_route summary baseline

**Command**

```python
run_route("traceability_barcode_summary", {"barcode": "PN-1001"}, routes=routes, config=config, format="records")
```

**Response JSON**

```json
{
  "rows": [
    {
      "barcode": "PN-1001",
      "barcode_prefix": "PN",
      "event_time": "2025-01-15T08:30:00",
      "file_hint": "/lake/panels/2025/PN-1001.parquet",
      "file_hint_route": "traceability_panel_file_hints",
      "station": "Laser Mark",
      "status": "Serial engraved",
      "table_route": "traceability_panel_events",
      "work_center": "Line A"
    },
    {
      "barcode": "PN-1001",
      "barcode_prefix": "PN",
      "event_time": "2025-01-15T09:00:00",
      "file_hint": "/lake/panels/2025/PN-1001.parquet",
      "file_hint_route": "traceability_panel_file_hints",
      "station": "AOI",
      "status": "Inspection passed",
      "table_route": "traceability_panel_events",
      "work_center": "Line A"
    },
    {
      "barcode": "PN-1001",
      "barcode_prefix": "PN",
      "event_time": "2025-01-15T11:20:00",
      "file_hint": "/lake/panels/2025/PN-1001.parquet",
      "file_hint_route": "traceability_panel_file_hints",
      "station": "Wave Solder",
      "status": "Solder joints complete",
      "table_route": "traceability_panel_events",
      "work_center": "Line A"
    },
    {
      "barcode": "PN-1001-M1",
      "barcode_prefix": "PN",
      "event_time": "2025-01-15T12:05:00",
      "file_hint": "/lake/modules/2025/PN-1001-modules.parquet",
      "file_hint_route": "traceability_module_file_hints",
      "station": "Module Assembly",
      "status": "Module M1 married to panel",
      "table_route": "traceability_module_events",
      "work_center": "Cell 3"
    },
    {
      "barcode": "PN-1001-M2",
      "barcode_prefix": "PN",
      "event_time": "2025-01-15T12:20:00",
      "file_hint": "/lake/modules/2025/PN-1001-modules.parquet",
      "file_hint_route": "traceability_module_file_hints",
      "station": "Module Assembly",
      "status": "Module M2 married to panel",
      "table_route": "traceability_module_events",
      "work_center": "Cell 3"
    }
  ]
}
```

### 8. HTTP /local/resolve

**Command**

```python
client.post("/local/resolve", json=http_payload)
```

**Request JSON**

```json
{
  "format": "json",
  "params": {
    "barcode": "PN-1001"
  },
  "record_analytics": true,
  "reference": "local:traceability_barcode_summary?column=table_route&column=event_time&column=status"
}
```

**Response JSON**

```json
{
  "charts": [],
  "columns": [
    "table_route",
    "event_time",
    "status"
  ],
  "description": "Resolve prefix-driven dependencies and merge traceability rows from nested local routes.",
  "elapsed_ms": 3.238,
  "limit": null,
  "offset": 0,
  "route_id": "traceability_barcode_summary",
  "row_count": 5,
  "rows": [
    {
      "event_time": "2025-01-15T08:30:00",
      "status": "Serial engraved",
      "table_route": "traceability_panel_events"
    },
    {
      "event_time": "2025-01-15T09:00:00",
      "status": "Inspection passed",
      "table_route": "traceability_panel_events"
    },
    {
      "event_time": "2025-01-15T11:20:00",
      "status": "Solder joints complete",
      "table_route": "traceability_panel_events"
    },
    {
      "event_time": "2025-01-15T12:05:00",
      "status": "Module M1 married to panel",
      "table_route": "traceability_module_events"
    },
    {
      "event_time": "2025-01-15T12:20:00",
      "status": "Module M2 married to panel",
      "table_route": "traceability_module_events"
    }
  ],
  "title": "Traceability summary",
  "total_rows": 5
}
```

**Notes**

- status_code: 200

### 9. HTTP /local/resolve error

**Command**

```python
client.post("/local/resolve", json={})
```

**Request JSON**

```json
{}
```

**Response JSON**

```json
{
  "detail": {
    "category": "ValidationError",
    "code": "missing_parameter",
    "hint": "Ensure the query string includes the documented parameter name.",
    "message": "reference is required"
  }
}
```

**Notes**

- status_code: 400
