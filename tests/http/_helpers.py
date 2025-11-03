from __future__ import annotations

from pathlib import Path
from typing import Callable

from tests.conftest import write_sidecar_route
from webbed_duck.config import Config, load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app

try:  # pragma: no cover - optional dependency guard
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover
    TestClient = None  # type: ignore


def build_test_client(
    tmp_path: Path,
    route_name: str,
    route_source: str,
    *,
    configure: Callable[[Config], None] | None = None,
) -> TestClient:
    """Compile ``route_source`` and return a configured :class:`TestClient`."""

    if TestClient is None:  # pragma: no cover - fastapi not installed
        raise RuntimeError("fastapi is required for HTTP integration tests")

    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    build.mkdir()

    write_sidecar_route(src, route_name, route_source)

    compile_routes(src, build)
    routes = load_compiled_routes(build)

    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    if configure is not None:
        configure(config)

    app = create_app(routes, config)
    client = TestClient(app)
    return client
