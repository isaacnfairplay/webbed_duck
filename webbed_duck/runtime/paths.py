from __future__ import annotations

from pathlib import Path

from webbed_duck.config import Config


def get_storage(cfg: Config) -> Path:
    runtime = getattr(cfg, "runtime", None)
    return runtime.storage if runtime is not None else Path(cfg.server.storage_root)


def storage_pages(cfg: Config, route_id: str) -> Path:
    return get_storage(cfg) / "pages" / route_id


def storage_db(cfg: Config) -> Path:
    return get_storage(cfg) / "db" / "app.sqlite3"
