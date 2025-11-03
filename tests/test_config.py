from __future__ import annotations

from pathlib import Path

import os

import pytest

from webbed_duck import config as config_mod
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


def test_load_config_parses_ui_chartjs_source(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        """
[ui]
chartjs_source = "https://cdn.example.com/chart.js"
""".strip(),
    )

    config = load_config(path)

    assert config.ui.chartjs_source == "https://cdn.example.com/chart.js"


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


def test_load_config_allows_storage_root_alias(tmp_path: Path) -> None:
    storage_root = tmp_path / "alias-root"
    path = _write_config(
        tmp_path,
        f"""
[storage]
root = "{storage_root.as_posix()}"
""".strip(),
    )

    config = load_config(path)

    assert config.server.storage_root == storage_root


def test_load_config_rejects_conflicting_storage_alias(tmp_path: Path) -> None:
    storage_root = tmp_path / "alias-root"
    server_root = tmp_path / "other-root"
    path = _write_config(
        tmp_path,
        f"""
[storage]
root = "{storage_root.as_posix()}"

[server]
storage_root = "{server_root.as_posix()}"
""".strip(),
    )

    with pytest.raises(ValueError, match="conflicts"):
        load_config(path)


def test_load_config_resolves_relative_storage_root(tmp_path: Path) -> None:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    config_path = config_dir / "config.toml"
    config_path.write_text(
        """
[server]
storage_root = "../custom-storage"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    expected = (config_dir / "../custom-storage").resolve()
    assert config.server.storage_root == expected


def test_load_config_rejects_unknown_storage_keys(tmp_path: Path) -> None:
    storage_root = tmp_path / "alias-root"
    path = _write_config(
        tmp_path,
        f"""
[storage]
root = "{storage_root.as_posix()}"
extra = true
""".strip(),
    )

    with pytest.raises(ValueError, match="unknown keys"):
        load_config(path)


def test_load_config_rejects_windows_path_on_posix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name == "nt":  # pragma: no cover - Windows validates directly
        pytest.skip("Windows paths are valid on Windows")
    path = _write_config(
        tmp_path,
        """
[storage]
root = "E:/web_storage"
""".strip(),
    )
    monkeypatch.setattr(config_mod, "_is_wsl", lambda: False)

    with pytest.raises(ValueError, match="Windows-style"):
        load_config(path)


def test_load_config_translates_windows_path_in_wsl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name == "nt":  # pragma: no cover - Windows already handles the path
        pytest.skip("WSL conversion only applies on POSIX hosts")
    mount_root = tmp_path / "mnt"
    (mount_root / "e").mkdir(parents=True)
    path = _write_config(
        tmp_path,
        """
[storage]
root = "E:/web_storage"
""".strip(),
    )
    monkeypatch.setattr(config_mod, "_is_wsl", lambda: True)
    monkeypatch.setattr(config_mod, "_WSL_MOUNT_ROOT", mount_root, raising=False)

    config = load_config(path)

    assert config.server.storage_root == mount_root / "e" / "web_storage"

