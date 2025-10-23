"""Configuration loading for webbed_duck."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

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
class UIConfig:
    """User interface toggles exposed to postprocessors."""

    show_http_warning: bool = True
    error_taxonomy_banner: bool = True


@dataclass(slots=True)
class AnalyticsConfig:
    """Runtime analytics collection controls."""

    enabled: bool = True
    weight_interactions: int = 1


@dataclass(slots=True)
class AuthConfig:
    """Authentication adapter selection and tunables."""

    mode: str = "none"
    external_adapter: str | None = None
    allowed_domains: Sequence[str] = field(default_factory=list)
    session_ttl_minutes: int = 45
    remember_me_days: int = 7


@dataclass(slots=True)
class Config:
    """Top-level configuration container."""

    server: ServerConfig = field(default_factory=ServerConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)


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
    ui_data = data.get("ui")
    if isinstance(ui_data, Mapping):
        cfg.ui = _parse_ui(ui_data, base=cfg.ui)
    analytics_data = data.get("analytics")
    if isinstance(analytics_data, Mapping):
        cfg.analytics = _parse_analytics(analytics_data, base=cfg.analytics)
    auth_data = data.get("auth")
    if isinstance(auth_data, Mapping):
        cfg.auth = _parse_auth(auth_data, base=cfg.auth)
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


def _parse_ui(data: Mapping[str, Any], base: UIConfig) -> UIConfig:
    overrides: MutableMapping[str, Any] = {}
    if "show_http_warning" in data:
        overrides["show_http_warning"] = bool(data["show_http_warning"])
    if "error_taxonomy_banner" in data:
        overrides["error_taxonomy_banner"] = bool(data["error_taxonomy_banner"])
    if not overrides:
        return base
    return replace(base, **overrides)


def _parse_analytics(data: Mapping[str, Any], base: AnalyticsConfig) -> AnalyticsConfig:
    overrides: MutableMapping[str, Any] = {}
    if "enabled" in data:
        overrides["enabled"] = bool(data["enabled"])
    if "weight_interactions" in data:
        overrides["weight_interactions"] = int(data["weight_interactions"])
    if not overrides:
        return base
    return replace(base, **overrides)


def _parse_auth(data: Mapping[str, Any], base: AuthConfig) -> AuthConfig:
    overrides: MutableMapping[str, Any] = {}
    if "mode" in data:
        overrides["mode"] = str(data["mode"])
    if "external_adapter" in data:
        overrides["external_adapter"] = str(data["external_adapter"]) if data["external_adapter"] is not None else None
    if "allowed_domains" in data and isinstance(data["allowed_domains"], Sequence):
        overrides["allowed_domains"] = [str(item) for item in data["allowed_domains"]]
    if "session_ttl_minutes" in data:
        overrides["session_ttl_minutes"] = int(data["session_ttl_minutes"])
    if "remember_me_days" in data:
        overrides["remember_me_days"] = int(data["remember_me_days"])
    if not overrides:
        return base
    return replace(base, **overrides)


__all__ = [
    "AnalyticsConfig",
    "Config",
    "ServerConfig",
    "UIConfig",
    "AuthConfig",
    "load_config",
]
