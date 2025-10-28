from __future__ import annotations

import importlib.resources as resources
import types
from pathlib import Path

import httpx
import pytest

from webbed_duck.server import app as server_app
from webbed_duck.server.vendor import (
    CHARTJS_FILENAME,
    DEFAULT_CHARTJS_SOURCE,
    ChartJSVendorResult,
    ensure_chartjs_vendor,
)
from webbed_duck.static.chartjs import CHARTJS_VERSION, SCRIPT_NAME


def test_bundled_chartjs_asset_present() -> None:
    asset = resources.files("webbed_duck.static.chartjs").joinpath(SCRIPT_NAME)
    assert asset.is_file(), "Packaged Chart.js asset missing"
    content = asset.read_bytes()
    assert len(content) > 100_000, "Packaged Chart.js asset unexpectedly small"


class _Response:
    def __init__(self, *, content: bytes = b"", status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)


class _FakeClient:
    def __init__(self, response: _Response | None = None, exc: Exception | None = None) -> None:
        self._response = response or _Response(content=b"console.log('chart');")
        self._exc = exc

    def __enter__(self) -> "_FakeClient":
        if self._exc:
            raise self._exc
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - context cleanup
        return None

    def get(self, url: str) -> _Response:
        if self._exc:
            raise self._exc
        return self._response


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEBDUCK_SKIP_CHARTJS_DOWNLOAD", raising=False)


def test_ensure_chartjs_vendor_uses_existing_asset(tmp_path: Path) -> None:
    asset_dir = tmp_path / "static" / "vendor" / "chartjs"
    asset_dir.mkdir(parents=True)
    target = asset_dir / CHARTJS_FILENAME
    target.write_bytes(b"console.log('existing');")

    result = ensure_chartjs_vendor(tmp_path)
    assert isinstance(result, ChartJSVendorResult)
    assert result.prepared is True
    assert result.error is None
    assert result.skipped is False


def test_ensure_chartjs_vendor_skips_via_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WEBDUCK_SKIP_CHARTJS_DOWNLOAD", "1")
    result = ensure_chartjs_vendor(tmp_path)
    assert result.prepared is False
    assert result.skipped is True
    assert result.error == "Chart.js download skipped via environment override"


def test_ensure_chartjs_vendor_handles_http_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _Boom(Exception):
        pass

    def fake_client(*args, **kwargs):
        return _FakeClient(exc=_Boom("boom"))

    monkeypatch.setattr(httpx, "Client", fake_client)

    result = ensure_chartjs_vendor(tmp_path)
    assert result.prepared is False
    assert result.error == "boom"


def test_ensure_chartjs_vendor_handles_write_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_client(*args, **kwargs):
        return _FakeClient()

    def fake_write_bytes(self, data):  # type: ignore[no-untyped-def]
        raise OSError("disk full")

    monkeypatch.setattr(httpx, "Client", fake_client)
    monkeypatch.setattr(Path, "write_bytes", fake_write_bytes)

    result = ensure_chartjs_vendor(tmp_path)
    assert result.prepared is False
    assert result.error == "disk full"


def test_prepare_chartjs_assets_sets_state(tmp_path: Path) -> None:
    asset_dir = tmp_path / "static" / "vendor" / "chartjs"
    asset_dir.mkdir(parents=True)
    target = asset_dir / CHARTJS_FILENAME
    target.write_text("console.log('inline');", encoding="utf-8")

    app = types.SimpleNamespace(state=types.SimpleNamespace())
    server_app._prepare_chartjs_assets(app, tmp_path)

    assert app.state.chartjs_asset_path == target
    assert app.state.chartjs_vendor_error is None
    assert app.state.chartjs_script_url == f"/vendor/{CHARTJS_FILENAME}?v={CHARTJS_VERSION}"


def test_prepare_chartjs_assets_falls_back_on_skip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WEBDUCK_SKIP_CHARTJS_DOWNLOAD", "true")

    app = types.SimpleNamespace(state=types.SimpleNamespace())
    server_app._prepare_chartjs_assets(app, tmp_path)

    expected_path = tmp_path / "static" / "vendor" / "chartjs" / CHARTJS_FILENAME
    assert app.state.chartjs_asset_path == expected_path
    assert app.state.chartjs_vendor_error == "Chart.js download skipped via environment override"
    assert app.state.chartjs_script_url == DEFAULT_CHARTJS_SOURCE
