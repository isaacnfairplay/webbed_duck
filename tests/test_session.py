from __future__ import annotations

import asyncio
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace

import pytest

from webbed_duck.config import AuthConfig, Config
from webbed_duck.server import session as session_module
from webbed_duck.server.auth import PseudoAuthAdapter, resolve_auth_adapter
from webbed_duck.server.meta import MetaStore
from webbed_duck.server.session import SESSION_COOKIE_NAME, SessionStore, StoredSession


def _make_store(tmp_path) -> tuple[SessionStore, MetaStore]:
    meta = MetaStore(tmp_path)
    config = AuthConfig()
    config.allowed_domains = ["example.com"]
    config.session_ttl_minutes = 30
    config.remember_me_days = 2
    store = SessionStore(meta, config)
    return store, meta


def test_session_store_create_resolve_and_destroy(monkeypatch, tmp_path) -> None:
    store, meta = _make_store(tmp_path)
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    future = base + timedelta(minutes=30)
    monkeypatch.setattr(session_module, "_utcnow", lambda: base)
    monkeypatch.setattr(session_module.secrets, "token_urlsafe", lambda _: "fixed-token")

    session = store.create(
        email="User@example.com ",
        user_agent="Browser/1.0",
        ip_address="192.168.1.42",
        remember_me=True,
    )
    assert session.email == "user@example.com"
    assert session.token == "fixed-token"
    assert session.expires_at == base + timedelta(days=2)

    with meta.connect() as conn:
        row = conn.execute(
            "SELECT token_hash, email, email_hash, user_agent_hash, ip_prefix FROM sessions"
        ).fetchone()
    assert row is not None
    expected_token_hash = hashlib.sha256(b"fixed-token").hexdigest()
    expected_email_hash = hashlib.sha256(b"user@example.com").hexdigest()
    assert row["token_hash"] == expected_token_hash
    assert row["email"] == "user@example.com"
    assert row["email_hash"] == expected_email_hash
    assert row["user_agent_hash"] is not None
    assert row["ip_prefix"] == "192.168.1"

    monkeypatch.setattr(session_module, "_utcnow", lambda: future)
    resolved = store.resolve(
        "fixed-token",
        user_agent="Browser/1.0",
        ip_address="192.168.1.99",
    )
    assert resolved is not None
    assert resolved.email == "user@example.com"
    assert resolved.email_hash == expected_email_hash

    store.destroy("fixed-token")
    with meta.connect() as conn:
        remaining = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert remaining == 0


def test_session_store_resolve_requires_matching_bindings(monkeypatch, tmp_path) -> None:
    store, _ = _make_store(tmp_path)
    base = datetime(2025, 6, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(session_module, "_utcnow", lambda: base)
    monkeypatch.setattr(session_module.secrets, "token_urlsafe", lambda _: "fixed-token")
    store.create(
        email="user@example.com",
        user_agent="Browser",
        ip_address="192.168.5.10",
        remember_me=False,
    )

    later = base + timedelta(minutes=10)
    monkeypatch.setattr(session_module, "_utcnow", lambda: later)
    assert (
        store.resolve("fixed-token", user_agent=None, ip_address="192.168.5.11")
        is None
    )
    assert (
        store.resolve("fixed-token", user_agent="Browser", ip_address="10.0.0.1")
        is None
    )
    assert (
        store.resolve("fixed-token", user_agent="Other", ip_address="192.168.5.99")
        is None
    )


def test_session_store_resolve_purges_expired(monkeypatch, tmp_path) -> None:
    store, meta = _make_store(tmp_path)
    store._config.session_ttl_minutes = 5
    base = datetime(2025, 7, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(session_module, "_utcnow", lambda: base)
    monkeypatch.setattr(session_module.secrets, "token_urlsafe", lambda _: "fixed-token")
    store.create(
        email="user@example.com",
        user_agent="Browser",
        ip_address="192.168.0.1",
        remember_me=False,
    )

    expired = base + timedelta(minutes=10)
    monkeypatch.setattr(session_module, "_utcnow", lambda: expired)
    assert (
        store.resolve("fixed-token", user_agent="Browser", ip_address="192.168.0.5")
        is None
    )
    with meta.connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert count == 0


def test_session_store_validate_email(tmp_path) -> None:
    store, _ = _make_store(tmp_path)
    assert store.validate_email(" User@Example.com ") == "user@example.com"
    with pytest.raises(ValueError):
        store.validate_email("not-an-email")
    with pytest.raises(ValueError):
        store.validate_email("user@other.com")


def test_pseudo_auth_adapter_success() -> None:
    stored = StoredSession(
        token="token",
        email="user@example.com",
        email_hash="hash",
        expires_at=datetime.now(timezone.utc),
    )

    class RecorderStore:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None, str | None]] = []

        def resolve(self, token: str, *, user_agent: str | None, ip_address: str | None):
            self.calls.append((token, user_agent, ip_address))
            return stored

    store = RecorderStore()
    adapter = PseudoAuthAdapter(store)  # type: ignore[arg-type]
    request = SimpleNamespace(
        cookies={SESSION_COOKIE_NAME: "token"},
        headers={"user-agent": "Browser"},
        client=SimpleNamespace(host="10.0.0.5"),
    )

    user = asyncio.run(adapter.authenticate(request))
    assert user is not None
    assert user.user_id == "user@example.com"
    assert user.email_hash == "hash"
    assert user.display_name == "user"
    assert store.calls == [("token", "Browser", "10.0.0.5")]


def test_pseudo_auth_adapter_missing_cookie() -> None:
    class Store:
        def __init__(self) -> None:
            self.called = False

        def resolve(self, *args, **kwargs):
            self.called = True
            return None

    store = Store()
    adapter = PseudoAuthAdapter(store)  # type: ignore[arg-type]
    request = SimpleNamespace(cookies={}, headers={}, client=None)

    result = asyncio.run(adapter.authenticate(request))
    assert result is None
    assert store.called is False


def test_pseudo_auth_adapter_resolve_none() -> None:
    class Store:
        def resolve(self, *args, **kwargs):
            return None

    adapter = PseudoAuthAdapter(Store())  # type: ignore[arg-type]
    request = SimpleNamespace(
        cookies={SESSION_COOKIE_NAME: "token"},
        headers={"user-agent": "Browser"},
        client=SimpleNamespace(host="127.0.0.1"),
    )

    assert asyncio.run(adapter.authenticate(request)) is None


def test_resolve_auth_adapter_requires_session_store_for_pseudo() -> None:
    config = Config()
    config.auth.mode = "pseudo"
    with pytest.raises(RuntimeError):
        resolve_auth_adapter("pseudo", config=config, session_store=None)


def test_resolve_auth_adapter_validates_external_factory(monkeypatch) -> None:
    module_name = "tests.fake_external_adapter"
    module = ModuleType(module_name)

    def build_adapter(config: Config):  # pragma: no cover - interface exercise
        return object()

    module.build_adapter = build_adapter  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module_name, module)

    config = Config()
    config.auth.mode = "external"
    config.auth.external_adapter = f"{module_name}:build_adapter"
    with pytest.raises(TypeError):
        resolve_auth_adapter("external", config=config, session_store=None)


def test_resolve_auth_adapter_external_factory_accepts_config(monkeypatch) -> None:
    module_name = "tests.fake_external_success"
    module = ModuleType(module_name)

    captured: dict[str, object] = {}

    class DummyAdapter:
        def __init__(self, cfg: Config) -> None:
            self.config = cfg

        async def authenticate(self, request):  # pragma: no cover - simple passthrough
            return None

    def build_adapter(config: Config) -> DummyAdapter:
        captured["config"] = config
        return DummyAdapter(config)

    module.build_adapter = build_adapter  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module_name, module)

    config = Config()
    config.auth.mode = "external"
    config.auth.external_adapter = f"{module_name}:build_adapter"

    adapter = resolve_auth_adapter("external", config=config, session_store=None)
    assert isinstance(adapter, DummyAdapter)
    assert captured["config"] is config
    assert adapter.config is config


def test_resolve_auth_adapter_external_factory_type_error_propagates(monkeypatch) -> None:
    module_name = "tests.fake_external_failure"
    module = ModuleType(module_name)

    def build_adapter(config: Config):
        raise TypeError("boom")

    module.build_adapter = build_adapter  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module_name, module)

    config = Config()
    config.auth.mode = "external"
    config.auth.external_adapter = f"{module_name}:build_adapter"

    with pytest.raises(TypeError) as excinfo:
        resolve_auth_adapter("external", config=config, session_store=None)
    assert "boom" in str(excinfo.value)


def test_resolve_auth_adapter_falls_back_to_anonymous() -> None:
    config = Config()
    adapter = resolve_auth_adapter("unknown", config=config, session_store=None)
    user = asyncio.run(adapter.authenticate(SimpleNamespace()))
    assert user is not None
    assert user.user_id == "anonymous"
