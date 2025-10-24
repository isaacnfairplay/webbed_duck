from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app


def test_load_config_supports_storage_section(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[storage]\nroot = \"custom_storage\"\n", encoding="utf-8")

    config = load_config(config_path)

    assert config.server.storage_root == Path("custom_storage")


def test_storage_section_does_not_override_server_block(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        [storage]
        root = "alias_storage"

        [server]
        storage_root = "explicit_storage"
        """
        .strip()
        + "\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.server.storage_root == Path("explicit_storage")


def test_create_app_ensures_storage_root_exists(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    storage_root = tmp_path / "nested" / "storage"
    config = load_config(None)
    config.server = replace(config.server, storage_root=storage_root)

    source_dir = tmp_path / "routes"
    source_dir.mkdir()
    route_path = source_dir / "hello.sql.md"
    route_path.write_text(
        """
        +++
        id = "hello"
        path = "/hello"
        +++

        ```sql
        SELECT 'world' AS greeting
        ```
        """
        .strip()
        + "\n",
        encoding="utf-8",
    )

    build_dir = tmp_path / "build"
    compile_routes(source_dir, build_dir)
    routes = load_compiled_routes(build_dir)

    assert not storage_root.exists()

    app = create_app(routes, config)

    assert storage_root.exists()
    assert getattr(app.state, "storage_root", None) == storage_root

