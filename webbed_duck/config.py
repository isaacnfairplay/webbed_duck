"""Configuration loading for webbed_duck."""
from __future__ import annotations

import contextlib
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib  # type: ignore


_WINDOWS_ABSOLUTE_PATH = re.compile(r"^(?P<drive>[A-Za-z]):[\\/](?P<rest>.*)$")
_WSL_MOUNT_ROOT: Path = Path("/mnt")


@dataclass(slots=True)
class ServerConfig:
    """HTTP server configuration."""

    storage_root: Path = Path("storage")
    host: str = "127.0.0.1"
    port: int = 8000
    source_dir: Path | None = Path("routes_src")
    build_dir: Path = Path("routes_build")
    auto_compile: bool = True
    watch: bool = False
    watch_interval: float = 1.0


@dataclass(slots=True)
class UIConfig:
    """User interface toggles exposed to postprocessors."""

    show_http_warning: bool = True
    error_taxonomy_banner: bool = True
    chartjs_source: str | None = None


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
class EmailConfig:
    """Outbound email adapter configuration."""

    adapter: str | None = None
    share_token_ttl_minutes: int = 90
    bind_share_to_user_agent: bool = False
    bind_share_to_ip_prefix: bool = False


@dataclass(slots=True)
class ShareConfig:
    """Share workflow configuration."""

    max_total_size_mb: int = 15
    zip_attachments: bool = True
    zip_passphrase_required: bool = False
    watermark: bool = True


@dataclass(slots=True)
class CacheConfig:
    """Materialized result cache configuration."""

    enabled: bool = True
    ttl_seconds: int = 24 * 3600
    page_rows: int = 500
    enforce_global_page_size: bool = False


@dataclass(slots=True)
class FeatureFlagsConfig:
    """Feature toggle configuration."""

    annotations_enabled: bool = False
    comments_enabled: bool = False
    tasks_enabled: bool = False
    overrides_enabled: bool = False


@dataclass(slots=True)
class Config:
    """Top-level configuration container."""

    server: ServerConfig = field(default_factory=ServerConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    share: ShareConfig = field(default_factory=ShareConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    feature_flags: FeatureFlagsConfig = field(default_factory=FeatureFlagsConfig)


def _is_wsl() -> bool:
    """Return ``True`` when running under Windows Subsystem for Linux."""

    if os.name != "posix":
        return False
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    with contextlib.suppress(OSError):
        release = Path("/proc/sys/kernel/osrelease").read_text().lower()
        if "microsoft" in release or "wsl" in release:
            return True
    return False


def _as_path(value: Any, *, relative_to: Path | None = None) -> Path:
    """Coerce ``value`` into a :class:`Path` with platform-aware semantics."""

    text = str(value)
    match = _WINDOWS_ABSOLUTE_PATH.match(text)
    if match:
        if os.name == "nt":
            path = Path(text)
        else:
            if not _is_wsl():
                raise ValueError(
                    "Windows-style absolute paths are not supported on this platform; "
                    "use a POSIX path such as '/mnt/c/...'."
                )
            drive = match.group("drive").lower()
            remainder = match.group("rest").replace("\\", "/")
            path = _WSL_MOUNT_ROOT / drive
            if remainder:
                path /= Path(remainder)
    else:
        path = Path(text)
    path = path.expanduser()
    if path.is_absolute():
        return path
    if relative_to is not None:
        return (relative_to / path).resolve(strict=False)
    return path


def _non_negative_int(value: Any) -> int:
    return max(0, int(value))


def _hours_to_seconds(value: Any) -> int:
    return _non_negative_int(float(value) * 3600)


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

    config_path = Path(path)
    data = _load_toml(config_path)
    base_dir = config_path.parent.resolve()
    storage_data = data.get("storage")
    storage_root_override: Path | None = None
    if isinstance(storage_data, Mapping):
        unknown_storage_keys = set(storage_data) - {"root"}
        if unknown_storage_keys:
            unknown = ", ".join(sorted(unknown_storage_keys))
            raise ValueError(f"storage.* contains unknown keys: {unknown}")
        if "root" in storage_data:
            storage_root_override = _as_path(
                storage_data["root"], relative_to=base_dir
            )

    server_data = data.get("server")
    server_declared_storage_root = False
    if isinstance(server_data, Mapping):
        server_declared_storage_root = "storage_root" in server_data
        cfg.server = _parse_server(
            server_data, base=cfg.server, relative_to=base_dir
        )

    if storage_root_override is not None:
        if (
            server_declared_storage_root
            and Path(cfg.server.storage_root) != storage_root_override
        ):
            raise ValueError(
                "storage.root conflicts with server.storage_root; choose one"
            )
        cfg.server.storage_root = storage_root_override
    ui_data = data.get("ui")
    if isinstance(ui_data, Mapping):
        cfg.ui = _parse_ui(ui_data, base=cfg.ui)
    analytics_data = data.get("analytics")
    if isinstance(analytics_data, Mapping):
        cfg.analytics = _parse_analytics(analytics_data, base=cfg.analytics)
    auth_data = data.get("auth")
    if isinstance(auth_data, Mapping):
        cfg.auth = _parse_auth(auth_data, base=cfg.auth)
    email_data = data.get("email")
    if isinstance(email_data, Mapping):
        cfg.email = _parse_email(email_data, base=cfg.email)
    share_data = data.get("share")
    if isinstance(share_data, Mapping):
        cfg.share = _parse_share(share_data, base=cfg.share)
    cache_data = data.get("cache")
    if isinstance(cache_data, Mapping):
        cfg.cache = _parse_cache(cache_data, base=cfg.cache)
    feature_flag_data = data.get("feature_flags")
    if isinstance(feature_flag_data, Mapping):
        cfg.feature_flags = _parse_feature_flags(feature_flag_data, base=cfg.feature_flags)
    return cfg


def _parse_server(
    data: Mapping[str, Any],
    base: ServerConfig,
    *,
    relative_to: Path | None = None,
) -> ServerConfig:
    overrides: MutableMapping[str, Any] = {}
    if "storage_root" in data:
        overrides["storage_root"] = _as_path(
            data["storage_root"], relative_to=relative_to
        )
    if "host" in data:
        overrides["host"] = str(data["host"])
    if "port" in data:
        port = int(data["port"])
        if port <= 0 or port >= 65536:
            raise ValueError("server.port must be between 1 and 65535")
        overrides["port"] = port
    if "source_dir" in data:
        overrides["source_dir"] = (
            None
            if data["source_dir"] is None
            else _as_path(data["source_dir"], relative_to=relative_to)
        )
    if "build_dir" in data:
        overrides["build_dir"] = _as_path(
            data["build_dir"], relative_to=relative_to
        )
    if "auto_compile" in data:
        overrides["auto_compile"] = bool(data["auto_compile"])
    if "watch" in data:
        overrides["watch"] = bool(data["watch"])
    if "watch_interval" in data:
        interval = float(data["watch_interval"])
        if interval <= 0:
            raise ValueError("server.watch_interval must be greater than zero")
        overrides["watch_interval"] = interval
    if not overrides:
        return base
    return replace(base, **overrides)


def _parse_ui(data: Mapping[str, Any], base: UIConfig) -> UIConfig:
    overrides: MutableMapping[str, Any] = {}
    if "show_http_warning" in data:
        overrides["show_http_warning"] = bool(data["show_http_warning"])
    if "error_taxonomy_banner" in data:
        overrides["error_taxonomy_banner"] = bool(data["error_taxonomy_banner"])
    if "chartjs_source" in data:
        value = data["chartjs_source"]
        overrides["chartjs_source"] = None if value is None else str(value)
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
    if "allowed_domains" in data:
        domains = data["allowed_domains"]
        if isinstance(domains, (str, bytes)) or not isinstance(domains, Sequence):
            raise ValueError("auth.allowed_domains must be a sequence of domain strings")
        overrides["allowed_domains"] = [str(item).strip() for item in domains if str(item).strip()]
    if "session_ttl_minutes" in data:
        overrides["session_ttl_minutes"] = int(data["session_ttl_minutes"])
    if "remember_me_days" in data:
        overrides["remember_me_days"] = int(data["remember_me_days"])
    if not overrides:
        return base
    return replace(base, **overrides)


def _parse_email(data: Mapping[str, Any], base: EmailConfig) -> EmailConfig:
    overrides: MutableMapping[str, Any] = {}
    if "adapter" in data:
        overrides["adapter"] = str(data["adapter"]) if data["adapter"] is not None else None
    if "share_token_ttl_minutes" in data:
        overrides["share_token_ttl_minutes"] = int(data["share_token_ttl_minutes"])
    if "bind_share_to_user_agent" in data:
        overrides["bind_share_to_user_agent"] = bool(data["bind_share_to_user_agent"])
    if "bind_share_to_ip_prefix" in data:
        overrides["bind_share_to_ip_prefix"] = bool(data["bind_share_to_ip_prefix"])
    if not overrides:
        return base
    return replace(base, **overrides)


def _parse_share(data: Mapping[str, Any], base: ShareConfig) -> ShareConfig:
    overrides: MutableMapping[str, Any] = {}
    if "max_total_size_mb" in data:
        overrides["max_total_size_mb"] = int(data["max_total_size_mb"])
    if "zip_attachments" in data:
        overrides["zip_attachments"] = bool(data["zip_attachments"])
    if "zip_passphrase_required" in data:
        overrides["zip_passphrase_required"] = bool(data["zip_passphrase_required"])
    if "watermark" in data:
        overrides["watermark"] = bool(data["watermark"])
    if not overrides:
        return base
    return replace(base, **overrides)


def _parse_cache(data: Mapping[str, Any], base: CacheConfig) -> CacheConfig:
    overrides: MutableMapping[str, Any] = {}
    if "enabled" in data:
        overrides["enabled"] = bool(data["enabled"])
    ttl_seconds: int | None = None
    if "ttl_seconds" in data:
        ttl_seconds = _non_negative_int(data["ttl_seconds"])
    if "ttl_hours" in data:
        ttl_seconds = _hours_to_seconds(data["ttl_hours"])
    if ttl_seconds is not None:
        overrides["ttl_seconds"] = ttl_seconds
    page_rows: int | None = None
    if "page_rows" in data:
        page_rows = _non_negative_int(data["page_rows"])
    if "rows_per_page" in data:
        page_rows = _non_negative_int(data["rows_per_page"])
    if page_rows is not None:
        overrides["page_rows"] = page_rows
    if "enforce_global_page_size" in data:
        overrides["enforce_global_page_size"] = bool(data["enforce_global_page_size"])
    if not overrides:
        return base
    return replace(base, **overrides)


def _parse_feature_flags(data: Mapping[str, Any], base: FeatureFlagsConfig) -> FeatureFlagsConfig:
    overrides: MutableMapping[str, Any] = {}
    for key in (
        "annotations_enabled",
        "comments_enabled",
        "tasks_enabled",
        "overrides_enabled",
    ):
        if key in data:
            overrides[key] = bool(data[key])
    if not overrides:
        return base
    return replace(base, **overrides)


__all__ = [
    "AnalyticsConfig",
    "Config",
    "ServerConfig",
    "UIConfig",
    "AuthConfig",
    "EmailConfig",
    "ShareConfig",
    "CacheConfig",
    "FeatureFlagsConfig",
    "load_config",
]
