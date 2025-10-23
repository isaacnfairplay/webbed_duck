"""Configuration loading for webbed_duck."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, MutableMapping

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib  # type: ignore


@dataclass(slots=True)
class ServerConfig:
    """HTTP server configuration."""

    storage_root: Path = Path("storage")
    theme: str = "system"
    host: str = "127.0.0.1"
    port: int = 8000


@dataclass(slots=True)
class Config:
    """Top-level configuration container."""

    server: ServerConfig = field(default_factory=ServerConfig)


def _as_path(value: Any) -> Path:
    if isinstance(value, Path):
        return value
    return Path(str(value))


def _load_toml(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_config(path: str | Path | None = None) -> Config:
    """Load configuration from ``path`` if provided, otherwise defaults.

    Parameters
    ----------
    path:
        Path to a ``config.toml`` file. When ``None`` the default configuration
        (with no file) is used.
    """

    cfg = Config()
    if path is None:
        return cfg

    data = _load_toml(Path(path))
    server_data = data.get("server")
    if isinstance(server_data, Mapping):
        cfg.server = _parse_server(server_data, base=cfg.server)
    return cfg


def _parse_server(data: Mapping[str, Any], base: ServerConfig) -> ServerConfig:
    overrides: MutableMapping[str, Any] = {}
    if "storage_root" in data:
        overrides["storage_root"] = _as_path(data["storage_root"])
    if "theme" in data:
        overrides["theme"] = str(data["theme"])
    if "host" in data:
        overrides["host"] = str(data["host"])
    if "port" in data:
        overrides["port"] = int(data["port"])
    if not overrides:
        return base
    return replace(base, **overrides)


__all__ = ["Config", "ServerConfig", "load_config"]
