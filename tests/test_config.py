from __future__ import annotations

from pathlib import Path

import pytest

from webbed_duck.config import load_config


def _write_config(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(content, encoding="utf-8")
    return path


def test_load_config_validates_basic_overrides(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        """
[server]
port = 8100
watch_interval = 0.5

[auth]
allowed_domains = ["example.com", "service.local"]
""".strip(),
    )

    config = load_config(path)
    assert config.server.port == 8100
    assert config.server.watch_interval == pytest.approx(0.5)
    assert config.auth.allowed_domains == ["example.com", "service.local"]


def test_load_config_rejects_invalid_port(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        """
[server]
port = 0
""".strip(),
    )

    with pytest.raises(ValueError, match="port"):
        load_config(path)


def test_load_config_rejects_invalid_watch_interval(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        """
[server]
watch_interval = 0
""".strip(),
    )

    with pytest.raises(ValueError, match="watch_interval"):
        load_config(path)


def test_load_config_requires_sequence_of_domains(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        """
[auth]
allowed_domains = "example.com"
""".strip(),
    )

    with pytest.raises(ValueError, match="allowed_domains"):
        load_config(path)


def test_load_config_parses_share_and_email_overrides(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        """
[email]
adapter = "tests.emailer:send"
bind_share_to_user_agent = true
bind_share_to_ip_prefix = true
share_token_ttl_minutes = 45

[share]
max_total_size_mb = 2
zip_attachments = false
zip_passphrase_required = true
watermark = false
""".strip(),
    )

    config = load_config(path)

    assert config.email.adapter == "tests.emailer:send"
    assert config.email.bind_share_to_user_agent is True
    assert config.email.bind_share_to_ip_prefix is True
    assert config.email.share_token_ttl_minutes == 45

    assert config.share.max_total_size_mb == 2
    assert config.share.zip_attachments is False
    assert config.share.zip_passphrase_required is True
    assert config.share.watermark is False


def test_load_config_parses_feature_flags(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        """
[feature_flags]
annotations_enabled = true
comments_enabled = false
""".strip(),
    )

    config = load_config(path)

    assert config.feature_flags.annotations_enabled is True
    assert config.feature_flags.comments_enabled is False
    assert config.feature_flags.tasks_enabled is False
    assert config.feature_flags.overrides_enabled is False


def test_load_config_cache_aliases_prefer_latest(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        """
[cache]
ttl_seconds = 90
ttl_hours = 0.5
page_rows = 250
rows_per_page = 150
enforce_global_page_size = true
""".strip(),
    )

    config = load_config(path)

    assert config.cache.ttl_seconds == 1800
    assert config.cache.page_rows == 150
    assert config.cache.enforce_global_page_size is True


def test_load_config_expands_user_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    path = _write_config(
        tmp_path,
        """
[server]
storage_root = "~/duck_storage"
source_dir = "~/routes"
build_dir = "~/build"
""".strip(),
    )

    config = load_config(path)

    assert config.server.storage_root == home / "duck_storage"
    assert config.server.source_dir == home / "routes"
    assert config.server.build_dir == home / "build"

