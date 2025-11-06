"""Deprecation coverage for the legacy ``webbed_duck.core`` surface."""
from __future__ import annotations

import datetime as dt
import importlib
import sys
import warnings
from pathlib import Path
from types import ModuleType

import pytest


def _reimport(module_name: str) -> tuple[ModuleType, list[warnings.WarningMessage]]:
    """Reload ``module_name`` and capture any deprecation warnings."""

    for name in [
        cached
        for cached in sys.modules
        if cached == module_name or cached.startswith(f"{module_name}.")
    ]:
        sys.modules.pop(name, None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        module = importlib.import_module(module_name)
    return module, list(caught)


def _assert_warning_emitted(caught: list[warnings.WarningMessage]) -> None:
    assert any(issubclass(item.category, DeprecationWarning) for item in caught)


def test_core_package_import_warns() -> None:
    _module, caught = _reimport("webbed_duck.core")
    _assert_warning_emitted(caught)


@pytest.mark.parametrize(
    "module_name",
    [
        "webbed_duck.core.compiler",
        "webbed_duck.core.incremental",
        "webbed_duck.core.local",
        "webbed_duck.core.routes",
    ],
)
def test_core_submodule_import_warns(module_name: str) -> None:
    _module, caught = _reimport(module_name)
    _assert_warning_emitted(caught)


def test_compile_routes_warns_on_call(tmp_path: Path) -> None:
    module, _caught = _reimport("webbed_duck.core.compiler")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        with pytest.raises(FileNotFoundError):
            module.compile_routes(tmp_path / "missing", tmp_path / "build")
    _assert_warning_emitted(list(caught))


def test_compile_route_file_warns_on_call(tmp_path: Path) -> None:
    module = importlib.import_module("webbed_duck.core.compiler")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        with pytest.raises(FileNotFoundError):
            module.compile_route_file(tmp_path / "example.toml")
    _assert_warning_emitted(list(caught))


def test_compile_route_text_warns_on_call(tmp_path: Path) -> None:
    module = importlib.import_module("webbed_duck.core.compiler")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        with pytest.raises(module.RouteCompilationError):
            module.compile_route_text("broken", source_path=tmp_path / "route.toml")
    _assert_warning_emitted(list(caught))


class _SentinelError(RuntimeError):
    """Marker exception for isolating control flow in deprecation tests."""


def test_run_incremental_warns(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = importlib.import_module("webbed_duck.core.incremental")

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise _SentinelError

    monkeypatch.setattr(module, "get_storage", lambda _config: tmp_path)
    monkeypatch.setattr(module, "_open_checkpoint_db", _explode)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        with pytest.raises(_SentinelError):
            module.run_incremental(
                "route",
                cursor_param="cursor",
                start=dt.date(2024, 1, 1),
                end=dt.date(2024, 1, 2),
                config=object(),
            )
    _assert_warning_emitted(list(caught))


def test_local_route_runner_warns_on_init(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = importlib.import_module("webbed_duck.core.local")

    class _Config:
        server = type("S", (), {"plugins_dir": tmp_path})()

    class _Overlay:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def reload(self) -> None:  # pragma: no cover - trivial stub
            return None

        def list_for_route(self, _route_id: str) -> list[object]:  # pragma: no cover
            return []

    monkeypatch.setattr(module, "load_compiled_routes", lambda _build_dir: [])
    monkeypatch.setattr(module, "load_config", lambda _config: _Config())
    monkeypatch.setattr(module, "get_storage", lambda _config: tmp_path)
    monkeypatch.setattr(module, "CacheStore", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(module, "OverlayStore", lambda *_args, **_kwargs: _Overlay())
    monkeypatch.setattr(module, "PluginLoader", lambda *_args, **_kwargs: object())

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        module.LocalRouteRunner(build_dir=tmp_path)
    _assert_warning_emitted(list(caught))


def test_run_route_warns_on_call(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("webbed_duck.core.local")

    class _Runner:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def run(self, *_args: object, **_kwargs: object) -> str:
            return "ok"

    monkeypatch.setattr(module, "LocalRouteRunner", _Runner)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        assert module.run_route("route") == "ok"
    _assert_warning_emitted(list(caught))


def test_load_compiled_routes_warns_on_call(tmp_path: Path) -> None:
    module = importlib.import_module("webbed_duck.core.routes")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        with pytest.raises(FileNotFoundError):
            module.load_compiled_routes(tmp_path / "missing")
    _assert_warning_emitted(list(caught))
