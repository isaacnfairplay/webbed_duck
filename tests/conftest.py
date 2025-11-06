# TODO[todo-tests-s8-i0j1]: Build comprehensive engine regression tests, perf harness, and CI guards per Step 8 before relying on the new stack.
from __future__ import annotations

import contextlib
import os
import re
import sys
import textwrap
import warnings
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator

if TYPE_CHECKING:
    from starlette.testclient import TestClient

import pytest

warnings.filterwarnings(
    "default",
    category=DeprecationWarning,
    module=r"^webbed_duck\.core",
)

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


@pytest.fixture
def plugins_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "plugins"
    root.mkdir()
    monkeypatch.setenv("WEBBED_DUCK_PLUGINS_DIR", root.as_posix())
    return root


@pytest.fixture(autouse=True)
def _auto_plugins_dir(plugins_dir: Path) -> None:
    # Ensures every test has an isolated plugins directory configured via env var.
    return None


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

    warnings.filterwarnings(
        "default",
        category=DeprecationWarning,
        module=r"^webbed_duck\.core",
    )

    config.addinivalue_line(
        "filterwarnings",
        "default::DeprecationWarning:webbed_duck\\.core",
    )
    config.addinivalue_line(
        "filterwarnings",
        "default::DeprecationWarning:webbed_duck\\.core.*",
    )

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


class _PseudoSessionHarness:
    """Manage pseudo-auth sessions for HTTP integration tests."""

    def __init__(self, client: "TestClient") -> None:
        from webbed_duck.server import session as session_module

        self.client = client
        self._session_store = self.client.app.state.session_store
        self._meta_store = self.client.app.state.meta
        self._created_tokens: list[str] = []
        self._session_module = session_module
        self._original_user_agent = self.client.headers.get("user-agent")
        self.client.headers.update({"user-agent": "pytest-pseudo/1.0"})

    def issue(
        self,
        *,
        email: str = "user@example.com",
        user_agent: str | None = None,
        remember_me: bool = False,
        expired: bool = False,
    ) -> object:
        if user_agent:
            self.client.headers.update({"user-agent": user_agent})
        payload = {"email": email}
        if remember_me:
            payload["remember_me"] = True
        response = self.client.post("/auth/pseudo/session", json=payload)
        response.raise_for_status()
        token = self.client.cookies.get(self._session_module.SESSION_COOKIE_NAME)
        if not token:
            raise RuntimeError("pseudo session cookie was not set")
        record = self._session_store.resolve(
            token,
            user_agent=self.client.headers.get("user-agent"),
            ip_address="testclient",
        )
        if record is None:
            raise RuntimeError("pseudo session could not be resolved")
        self._created_tokens.append(token)
        if expired:
            self.expire(token)
        return record

    def expire(self, token: str) -> None:
        serialize_datetime = self._session_module.serialize_datetime
        utcnow = self._session_module._utcnow  # type: ignore[attr-defined]
        hash_token = self._session_module._hash_token  # type: ignore[attr-defined]
        expired_at = serialize_datetime(utcnow() - timedelta(minutes=1))
        with self._meta_store.connect() as conn:
            conn.execute(
                "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
                (expired_at, hash_token(token)),
            )
            conn.commit()

    def cleanup(self) -> None:
        for token in self._created_tokens:
            with contextlib.suppress(Exception):
                self._session_store.destroy(token)
        self.client.cookies.clear()
        if self._original_user_agent is None:
            self.client.headers.pop("user-agent", None)
        else:
            self.client.headers.update({"user-agent": self._original_user_agent})


@pytest.fixture
def pseudo_session_factory():
    """Return a factory that provisions pseudo-auth sessions with cleanup."""

    helpers: list[_PseudoSessionHarness] = []

    def factory(client: "TestClient") -> _PseudoSessionHarness:
        helper = _PseudoSessionHarness(client)
        helpers.append(helper)
        return helper

    yield factory

    for helper in helpers:
        helper.cleanup()


@pytest.fixture
def failing_email_sender():
    """Patch the FastAPI app's email sender to raise predictable failures."""

    installs: list[tuple[object, Callable[[], None]]] = []

    def installer(app, exception: Exception | None = None) -> Callable[[], None]:
        previous = getattr(app.state, "email_sender", None)

        def restore() -> None:
            app.state.email_sender = previous

        def failing_sender(*_args, **_kwargs):  # pragma: no cover - helper stub
            raise exception or RuntimeError("email adapter failure")

        app.state.email_sender = failing_sender
        installs.append((app, restore))
        return restore

    yield installer

    for _app, restore in reversed(installs):
        restore()


@pytest.fixture
def analytics_toggle():
    """Temporarily adjust the app's analytics-enabled flag with cleanup."""

    toggles: list[tuple[object, bool]] = []

    def toggle(app, *, enabled: bool) -> None:
        previous = bool(getattr(app.state.analytics, "_enabled", True))
        app.state.analytics._enabled = bool(enabled)
        toggles.append((app, previous))

    yield toggle

    for app, previous in reversed(toggles):
        app.state.analytics._enabled = previous
