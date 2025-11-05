from __future__ import annotations

from pathlib import Path

from webbed_duck.config import Config


def get_storage(cfg: Config) -> Path:
    try:
        runtime = cfg.runtime
    except AttributeError as exc:  # pragma: no cover - defensive
        raise RuntimeError("Config missing runtime section") from exc

    storage = getattr(runtime, "storage", None)
    if storage is None:
        raise RuntimeError("Config runtime.storage is not set")
    return storage


def storage_pages(cfg: Config, route_id: str) -> Path:
    return get_storage(cfg) / "pages" / route_id


def storage_db(cfg: Config) -> Path:
    return get_storage(cfg) / "db" / "app.sqlite3"
