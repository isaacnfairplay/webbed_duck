from __future__ import annotations

import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Iterator

import pytest

try:
    from hypothesis import HealthCheck, settings
except ImportError:  # pragma: no cover - hypothesis is optional in some environments
    HealthCheck = None  # type: ignore[assignment]
    settings = None  # type: ignore[assignment]

SQL_BLOCK_PATTERN = re.compile(r"```sql\s*(?P<sql>.*?)```", re.DOTALL | re.IGNORECASE)


def write_sidecar_route(base: Path, name: str, content: str) -> None:
    """Materialise a TOML/SQL sidecar route from legacy markdown-style text."""

    text = textwrap.dedent(content).strip()
    if not text.startswith("+++"):
        raise ValueError("Route definitions must start with TOML frontmatter")

    first = text.find("+++")
    second = text.find("+++", first + 3)
    if second == -1:
        raise ValueError("Route definitions must contain closing frontmatter delimiter")

    frontmatter = text[first + 3 : second].strip()
    body = text[second + 3 :].strip()

    match = SQL_BLOCK_PATTERN.search(body)
    if not match:
        raise ValueError("Route definitions must contain a ```sql``` block")

    sql = match.group("sql").strip()
    doc = (body[: match.start()] + body[match.end() :]).strip()

    (base / f"{name}.toml").write_text(frontmatter + "\n", encoding="utf-8")
    (base / f"{name}.sql").write_text(sql + "\n", encoding="utf-8")
    if doc:
        (base / f"{name}.md").write_text(doc + "\n", encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom command line options for the test suite."""

    group = parser.getgroup("webbed_duck")
    group.addoption(
        "--hypothesis-profile",
        action="store",
        default=None,
        help="Select the Hypothesis profile to load (dev, ci, or stress).",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Declare pytest markers and configure Hypothesis defaults."""

    for marker, description in [
        ("duckdb", "Tests that interact with DuckDB connections or files."),
        (
            "integration",
            "Tests that span multiple subsystems or require compiled routes.",
        ),
        ("docs", "Tests that validate documentation examples or narratives."),
    ]:
        config.addinivalue_line("markers", f"{marker}: {description}")

    default_profile = _configure_hypothesis_profiles()
    if settings is None:
        return

    selected = config.getoption("hypothesis_profile")
    if selected:
        settings.load_profile(selected)
    elif os.getenv("CI"):
        settings.load_profile("ci")
    else:
        settings.load_profile(default_profile)


_HYPOTHESIS_PROFILES_REGISTERED = False


def _configure_hypothesis_profiles() -> str:
    """Register Hypothesis profiles and return the default profile name."""

    global _HYPOTHESIS_PROFILES_REGISTERED
    if settings is None:
        return "dev"

    if not _HYPOTHESIS_PROFILES_REGISTERED:
        suppress_checks = (HealthCheck.filter_too_much,) if HealthCheck else ()
        settings.register_profile(
            "dev",
            settings(
                max_examples=25,
                deadline=500,
                suppress_health_check=suppress_checks,
            ),
        )
        settings.register_profile(
            "ci",
            settings(
                max_examples=75,
                deadline=750,
                print_blob=True,
                suppress_health_check=suppress_checks,
            ),
        )
        settings.register_profile(
            "stress",
            settings(
                max_examples=150,
                deadline=None,
                print_blob=True,
                suppress_health_check=suppress_checks,
            ),
        )
        _HYPOTHESIS_PROFILES_REGISTERED = True
    return "dev"


@pytest.fixture
def duckdb_connection(tmp_path_factory: pytest.TempPathFactory):
    """Yield a configured DuckDB connection backed by a temporary database file."""

    from tests.utils import duckdb as duckdb_utils

    with duckdb_utils.temporary_database(tmp_path_factory) as (connection, _path):
        duckdb_utils.configure_test_connection(connection)
        yield connection


@pytest.fixture
def duckdb_database_path(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Return the path to a temporary DuckDB database file."""

    from tests.utils import duckdb as duckdb_utils

    with duckdb_utils.temporary_database(tmp_path_factory) as (_connection, path):
        yield path


@pytest.fixture
def temporary_storage(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Provide an isolated storage root for filesystem-heavy tests."""

    from tests.utils import storage as storage_utils

    with storage_utils.temporary_storage(tmp_path_factory) as path:
        yield path
