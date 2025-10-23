from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from ..config import Config, load_config
from .local import run_route


@dataclass(slots=True)
class IncrementalResult:
    route_id: str
    cursor_param: str
    value: str
    rows_returned: int


def run_incremental(
    route_id: str,
    *,
    cursor_param: str,
    start: dt.date,
    end: dt.date,
    config: Config | None = None,
    build_dir: str | Path = "routes_build",
) -> list[IncrementalResult]:
    """Run ``route_id`` for each day in ``[start, end]`` inclusive."""

    if config is None:
        config = load_config(None)
    checkpoints = _load_checkpoints(config.server.storage_root)
    last_value = checkpoints.get(route_id, {}).get(cursor_param)

    results: list[IncrementalResult] = []
    current = start
    while current <= end:
        iso_value = current.isoformat()
        if last_value and iso_value <= last_value:
            current += dt.timedelta(days=1)
            continue
        table = run_route(
            route_id,
            params={cursor_param: iso_value},
            build_dir=build_dir,
            config=config,
            format="arrow",
        )
        results.append(
            IncrementalResult(
                route_id=route_id,
                cursor_param=cursor_param,
                value=iso_value,
                rows_returned=table.num_rows,
            )
        )
        checkpoints.setdefault(route_id, {})[cursor_param] = iso_value
        _save_checkpoints(config.server.storage_root, checkpoints)
        current += dt.timedelta(days=1)
    return results


def _load_checkpoints(storage_root: Path) -> dict[str, dict[str, str]]:
    path = Path(storage_root) / "runtime" / "checkpoints.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_checkpoints(storage_root: Path, data: dict[str, dict[str, str]]) -> None:
    path = Path(storage_root) / "runtime" / "checkpoints.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


__all__ = ["IncrementalResult", "run_incremental"]
