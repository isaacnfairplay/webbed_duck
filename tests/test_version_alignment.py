from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for Python < 3.11
    import tomli as tomllib  # type: ignore[import-not-found]

from webbed_duck import __version__


def test_package_version_matches_pyproject() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    contents = pyproject_path.read_text(encoding="utf-8")
    version = tomllib.loads(contents)["project"]["version"]
    assert __version__ == version
