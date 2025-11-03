"""Comprehensive configuration surface regression tests.

Timeline
--------
T0  Audit defaults for every dataclass.
T1  Enumerate override scenarios across sections.
T2  Stress conversion helpers and edge paths.
T3  Validate error handling for conflicting or malformed input.

This module focuses on expanding the matrix of configuration coverage
without mutating the core library. Each parametrised test documents the
rationale in its docstring to aid future maintainers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pytest

from webbed_duck.config import (
    Config,
    _as_path,
    _hours_to_seconds,
    _non_negative_int,
    _parse_auth,
    _parse_email,
    _parse_server,
    _parse_ui,
    load_config,
)


def _toml_literal(value: Any) -> str:
    """Render a Python value into an inline TOML representation."""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (Path, str)):
        text = str(value).replace("\\", "\\\\")
        return f'"{text}"'
    if isinstance(value, Iterable):
        inner = ", ".join(_toml_literal(item) for item in value)
        return f"[{inner}]"
    raise TypeError(f"Unsupported TOML literal: {value!r}")


SERVER_DEFAULTS = [
    ("storage_root", Path("storage")),
    ("host", "127.0.0.1"),
    ("port", 8000),
    ("source_dir", Path("routes_src")),
    ("build_dir", Path("routes_build")),
    ("auto_compile", True),
    ("watch", False),
    ("watch_interval", 1.0),
]


@pytest.mark.parametrize(
    ("field", "expected"),
    SERVER_DEFAULTS,
    ids=[name for name, _ in SERVER_DEFAULTS],
)
def test_server_config_defaults(field: str, expected: Any) -> None:
    """Verify that :class:`ServerConfig` default values remain stable."""

    cfg = Config()
    assert getattr(cfg.server, field) == expected


UI_DEFAULTS = [
    ("show_http_warning", True),
    ("error_taxonomy_banner", True),
    ("chartjs_source", None),
]


@pytest.mark.parametrize(
    ("field", "expected"),
    UI_DEFAULTS,
    ids=[name for name, _ in UI_DEFAULTS],
)
def test_ui_config_defaults(field: str, expected: Any) -> None:
    """Track the default UI presentation toggles."""

    cfg = Config()
    assert getattr(cfg.ui, field) == expected


ANALYTICS_DEFAULTS = [
    ("enabled", True),
    ("weight_interactions", 1),
]


@pytest.mark.parametrize(
    ("field", "expected"),
    ANALYTICS_DEFAULTS,
    ids=[name for name, _ in ANALYTICS_DEFAULTS],
)
def test_analytics_config_defaults(field: str, expected: Any) -> None:
    """Guard the analytics defaults that power usage telemetry."""

    cfg = Config()
    assert getattr(cfg.analytics, field) == expected


AUTH_DEFAULTS = [
    ("mode", "none"),
    ("external_adapter", None),
    ("allowed_domains", []),
    ("session_ttl_minutes", 45),
    ("remember_me_days", 7),
]


@pytest.mark.parametrize(
    ("field", "expected"),
    AUTH_DEFAULTS,
    ids=[name for name, _ in AUTH_DEFAULTS],
)
def test_auth_config_defaults(field: str, expected: Any) -> None:
    """Ensure authentication defaults reflect the intranet posture."""

    cfg = Config()
    assert getattr(cfg.auth, field) == expected


EMAIL_DEFAULTS = [
    ("adapter", None),
    ("share_token_ttl_minutes", 90),
    ("bind_share_to_user_agent", False),
    ("bind_share_to_ip_prefix", False),
]


@pytest.mark.parametrize(
    ("field", "expected"),
    EMAIL_DEFAULTS,
    ids=[name for name, _ in EMAIL_DEFAULTS],
)
def test_email_config_defaults(field: str, expected: Any) -> None:
    """Cover outbound email adapter defaults and security toggles."""

    cfg = Config()
    assert getattr(cfg.email, field) == expected


SHARE_DEFAULTS = [
    ("max_total_size_mb", 15),
    ("zip_attachments", True),
    ("zip_passphrase_required", False),
    ("watermark", True),
]


@pytest.mark.parametrize(
    ("field", "expected"),
    SHARE_DEFAULTS,
    ids=[name for name, _ in SHARE_DEFAULTS],
)
def test_share_config_defaults(field: str, expected: Any) -> None:
    """Keep share workflow defaults aligned with documentation promises."""

    cfg = Config()
    assert getattr(cfg.share, field) == expected


CACHE_DEFAULTS = [
    ("enabled", True),
    ("ttl_seconds", 24 * 3600),
    ("page_rows", 500),
    ("enforce_global_page_size", False),
]


@pytest.mark.parametrize(
    ("field", "expected"),
    CACHE_DEFAULTS,
    ids=[name for name, _ in CACHE_DEFAULTS],
)
def test_cache_config_defaults(field: str, expected: Any) -> None:
    """Snapshot default cache retention and pagination behaviour."""

    cfg = Config()
    assert getattr(cfg.cache, field) == expected


FEATURE_FLAG_DEFAULTS = [
    ("annotations_enabled", False),
    ("comments_enabled", False),
    ("tasks_enabled", False),
    ("overrides_enabled", False),
]


@pytest.mark.parametrize(
    ("field", "expected"),
    FEATURE_FLAG_DEFAULTS,
    ids=[name for name, _ in FEATURE_FLAG_DEFAULTS],
)
def test_feature_flag_defaults(field: str, expected: Any) -> None:
    """Catch regressions in feature flag defaults that impact UI flows."""

    cfg = Config()
    assert getattr(cfg.feature_flags, field) == expected


CONFIG_OVERRIDE_CASES = [
    ("server", "host", "0.0.0.0", "host", "0.0.0.0"),
    ("server", "host", "intranet.local", "host", "intranet.local"),
    ("server", "port", 9000, "port", 9000),
    ("server", "port", 65535, "port", 65535),
    ("server", "auto_compile", False, "auto_compile", False),
    ("server", "auto_compile", True, "auto_compile", True),
    ("server", "watch", True, "watch", True),
    ("server", "watch", False, "watch", False),
    ("server", "watch_interval", 2.5, "watch_interval", 2.5),
    ("server", "watch_interval", 0.75, "watch_interval", 0.75),
    ("server", "storage_root", "data/storage", "storage_root", Path("data/storage")),
    ("server", "build_dir", "compiled_routes", "build_dir", Path("compiled_routes")),
    ("server", "source_dir", "source_routes", "source_dir", Path("source_routes")),
    ("ui", "show_http_warning", False, "show_http_warning", False),
    ("ui", "error_taxonomy_banner", False, "error_taxonomy_banner", False),
    ("ui", "chartjs_source", "https://cdn.example.com/chart.js", "chartjs_source", "https://cdn.example.com/chart.js"),
    ("analytics", "enabled", False, "enabled", False),
    ("analytics", "enabled", True, "enabled", True),
    ("analytics", "weight_interactions", 5, "weight_interactions", 5),
    ("analytics", "weight_interactions", 0, "weight_interactions", 0),
    ("auth", "mode", "pseudo", "mode", "pseudo"),
    ("auth", "mode", "external", "mode", "external"),
    ("auth", "external_adapter", "custom.auth:adapter", "external_adapter", "custom.auth:adapter"),
    ("auth", "allowed_domains", ["example.com", " corp.local "], "allowed_domains", ["example.com", "corp.local"]),
    ("auth", "allowed_domains", [], "allowed_domains", []),
    ("auth", "session_ttl_minutes", 60, "session_ttl_minutes", 60),
    ("auth", "session_ttl_minutes", 5, "session_ttl_minutes", 5),
    ("auth", "remember_me_days", 30, "remember_me_days", 30),
    ("auth", "remember_me_days", 1, "remember_me_days", 1),
    ("email", "adapter", "module:send_email", "adapter", "module:send_email"),
    ("email", "share_token_ttl_minutes", 120, "share_token_ttl_minutes", 120),
    ("email", "share_token_ttl_minutes", 15, "share_token_ttl_minutes", 15),
    ("email", "bind_share_to_user_agent", True, "bind_share_to_user_agent", True),
    ("email", "bind_share_to_user_agent", False, "bind_share_to_user_agent", False),
    ("email", "bind_share_to_ip_prefix", True, "bind_share_to_ip_prefix", True),
    ("email", "bind_share_to_ip_prefix", False, "bind_share_to_ip_prefix", False),
    ("share", "max_total_size_mb", 5, "max_total_size_mb", 5),
    ("share", "max_total_size_mb", 50, "max_total_size_mb", 50),
    ("share", "zip_attachments", False, "zip_attachments", False),
    ("share", "zip_attachments", True, "zip_attachments", True),
    ("share", "zip_passphrase_required", True, "zip_passphrase_required", True),
    ("share", "zip_passphrase_required", False, "zip_passphrase_required", False),
    ("share", "watermark", False, "watermark", False),
    ("share", "watermark", True, "watermark", True),
    ("cache", "enabled", False, "enabled", False),
    ("cache", "enabled", True, "enabled", True),
    ("cache", "ttl_seconds", 1800, "ttl_seconds", 1800),
    ("cache", "ttl_seconds", 0, "ttl_seconds", 0),
    ("cache", "ttl_hours", 0.5, "ttl_seconds", _hours_to_seconds(0.5)),
    ("cache", "ttl_hours", 1.75, "ttl_seconds", _hours_to_seconds(1.75)),
    ("cache", "page_rows", 250, "page_rows", 250),
    ("cache", "page_rows", 0, "page_rows", 0),
    ("cache", "rows_per_page", 125, "page_rows", 125),
    ("cache", "rows_per_page", 2000, "page_rows", 2000),
    ("cache", "enforce_global_page_size", True, "enforce_global_page_size", True),
    ("cache", "enforce_global_page_size", False, "enforce_global_page_size", False),
    ("feature_flags", "annotations_enabled", True, "annotations_enabled", True),
    ("feature_flags", "annotations_enabled", False, "annotations_enabled", False),
    ("feature_flags", "comments_enabled", True, "comments_enabled", True),
    ("feature_flags", "comments_enabled", False, "comments_enabled", False),
    ("feature_flags", "tasks_enabled", True, "tasks_enabled", True),
    ("feature_flags", "tasks_enabled", False, "tasks_enabled", False),
    ("feature_flags", "overrides_enabled", True, "overrides_enabled", True),
    ("feature_flags", "overrides_enabled", False, "overrides_enabled", False),
]


@pytest.mark.parametrize(
    ("section", "toml_key", "raw_value", "attribute", "expected"),
    CONFIG_OVERRIDE_CASES,
    ids=[f"{section}.{toml_key}" for section, toml_key, *_ in CONFIG_OVERRIDE_CASES],
)
def test_load_config_bulk_overrides(
    tmp_path: Path,
    section: str,
    toml_key: str,
    raw_value: Any,
    attribute: str,
    expected: Any,
) -> None:
    """Validate that declarative overrides persist correctly across sections."""

    config_text = f"[{section}]\n{toml_key} = {_toml_literal(raw_value)}\n"
    path = tmp_path / "config.toml"
    path.write_text(config_text, encoding="utf-8")

    config = load_config(path)
    section_obj = getattr(config, section)
    actual = getattr(section_obj, attribute)
    if isinstance(expected, Path):
        if not expected.is_absolute() and actual is not None:
            expected = (path.parent / expected).resolve(strict=False)
        assert actual == expected
    else:
        assert actual == expected


NON_NEGATIVE_CASES = [
    (0, 0),
    (-1, 0),
    (5, 5),
    (123456789, 123456789),
    (3.7, 3),
    (-12.5, 0),
    (9999999999, 9999999999),
    (1.999, 1),
    (2.001, 2),
    (True, 1),
    (False, 0),
    ("42", 42),
    ("-7", 0),
    (b"8", 8),
    (1.0e6, 1000000),
    (-1.0e6, 0),
    (0.0001, 0),
    (3.14159, 3),
    (2**16, 65536),
    (2**32, 4294967296),
]


@pytest.mark.parametrize(
    ("value", "expected"),
    NON_NEGATIVE_CASES,
    ids=[f"case-{index}" for index, _ in enumerate(NON_NEGATIVE_CASES, start=1)],
)
def test_non_negative_int_coercion_matrix(value: Any, expected: int) -> None:
    """Exercise ``_non_negative_int`` across integers, floats, strings, and booleans."""

    assert _non_negative_int(value) == expected


HOURS_TO_SECONDS_CASES = [
    (0, 0),
    (0.25, 900),
    (0.5, 1800),
    (1, 3600),
    (1.5, 5400),
    (2, 7200),
    (3.75, 13500),
    (10, 36000),
    (24, 86400),
    (1 / 60, 60),
    (0.01, 36),
    (12.3456, int(12.3456 * 3600)),
    (100, 360000),
    (0.3333333, int(0.3333333 * 3600)),
    (7.777, int(7.777 * 3600)),
]


@pytest.mark.parametrize(
    ("value", "expected"),
    HOURS_TO_SECONDS_CASES,
    ids=[f"hours-{value}" for value, _ in HOURS_TO_SECONDS_CASES],
)
def test_hours_to_seconds_matrix(value: Any, expected: int) -> None:
    """Confirm hour-to-second coercion keeps rounding consistent."""

    assert _hours_to_seconds(value) == expected


PATH_CASES = [
    ("data/output", False, "data/output"),
    ("./relative/path", False, "relative/path"),
    ("../up/one", False, "../up/one"),
    ("~/archive", False, str(Path("~/archive").expanduser())),
    ("/tmp/absolute", False, "/tmp/absolute"),
    (Path("explicit/path"), False, "explicit/path"),
    (Path("./explicit/relative"), True, "explicit/relative"),
    ("nested/file.txt", True, "nested/file.txt"),
    ("./dot/prefix", True, "dot/prefix"),
    ("../escape", True, "../escape"),
    ("with spaces/name", True, "with spaces/name"),
    ("./", True, "."),
    ("subdir", False, "subdir"),
    (Path(".."), True, ".."),
    ("levels/deep/file.sql", True, "levels/deep/file.sql"),
]


@pytest.mark.parametrize(
    ("raw", "use_relative", "expected_suffix"),
    PATH_CASES,
    ids=[f"path-{index}" for index, _ in enumerate(PATH_CASES, start=1)],
)
def test_as_path_matrix(tmp_path: Path, raw: Any, use_relative: bool, expected_suffix: str) -> None:
    """Assess ``_as_path`` behaviour under relative and absolute contexts."""

    base = tmp_path if use_relative else None
    result = _as_path(raw, relative_to=base)
    if base is None:
        assert str(result).endswith(expected_suffix)
    else:
        assert result == (base / Path(expected_suffix)).resolve(strict=False)


def test_parse_server_allows_none_source_dir() -> None:
    """Setting ``server.source_dir`` to ``None`` should disable compilation gracefully."""

    base = Config().server
    result = _parse_server({"source_dir": None}, base)
    assert result.source_dir is None


def test_parse_ui_allows_none_chartjs_source() -> None:
    """``ui.chartjs_source`` accepts explicit ``None`` assignments via API usage."""

    base = Config().ui
    result = _parse_ui({"chartjs_source": None}, base)
    assert result.chartjs_source is None


def test_parse_auth_allows_none_external_adapter() -> None:
    """``auth.external_adapter`` accepts ``None`` to clear adapters programmatically."""

    base = Config().auth
    result = _parse_auth({"external_adapter": None}, base)
    assert result.external_adapter is None


def test_parse_email_allows_none_adapter() -> None:
    """``email.adapter`` may be cleared to ``None`` for pseudo-share only deployments."""

    base = Config().email
    result = _parse_email({"adapter": None}, base)
    assert result.adapter is None


INVALID_CONFIG_CASES = [
    """
    [storage]
    root = "storage"
    extra = "boom"
    """,
    """
    [storage]
    root = "one"

    [server]
    storage_root = "two"
    """,
    """
    [auth]
    allowed_domains = "not-a-list"
    """,
    """
    [server]
    port = 70000
    """,
    """
    [server]
    watch_interval = 0
    """,
]


@pytest.mark.parametrize(
    "config_snippet",
    INVALID_CONFIG_CASES,
    ids=[f"invalid-{index}" for index, _ in enumerate(INVALID_CONFIG_CASES, start=1)],
)
def test_invalid_config_inputs_raise(tmp_path: Path, config_snippet: str) -> None:
    """Exercise defensive branches that reject unsupported configuration."""

    path = tmp_path / "config.toml"
    path.write_text(config_snippet.strip() + "\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_config(path)
