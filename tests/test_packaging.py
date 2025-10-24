from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def test_wheel_contains_webbed_duck_package(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "wheel", ".", "-w", str(dist_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - surfaces build logs
        raise AssertionError(f"pip wheel failed: {exc.stderr}") from exc

    wheels = list(dist_dir.glob("webbed_duck-*.whl"))
    assert wheels, "pip wheel did not produce a webbed_duck wheel"
    wheel_path = wheels[0]

    try:
        with zipfile.ZipFile(wheel_path) as archive:
            members = {name for name in archive.namelist() if not name.endswith("/")}

        assert "webbed_duck/__init__.py" in members, "Wheel is missing the root package"
        # Ensure submodules are packaged under the correct prefix rather than at the root.
        assert any(name.startswith("webbed_duck/core/") for name in members)
        leaked = {
            name
            for name in members
            if name.startswith("core/")
            or name.startswith("plugins/")
            or name.startswith("server/")
        }
        assert not leaked, "Wheel leaked top-level modules without the webbed_duck prefix"
    finally:
        egg_info = Path("webbed_duck.egg-info")
        if egg_info.exists():
            shutil.rmtree(egg_info)
