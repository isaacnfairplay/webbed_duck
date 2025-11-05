from __future__ import annotations

from pathlib import Path

from webbed_duck.config import Config


def get_storage(cfg: Config) -> Path:
    return cfg.runtime.storage


def storage_pages(cfg: Config, route_id: str) -> Path:
    return get_storage(cfg) / "pages" / route_id


def storage_db(cfg: Config) -> Path:
    return get_storage(cfg) / "db" / "app.sqlite3"
