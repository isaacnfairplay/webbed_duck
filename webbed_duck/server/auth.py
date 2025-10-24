from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Callable, Dict, Protocol, runtime_checkable

from fastapi import Request

from ..config import Config
from .session import SESSION_COOKIE_NAME, SessionStore


@dataclass(slots=True)
class AuthenticatedUser:
    user_id: str
    email_hash: str | None = None
    display_name: str | None = None


@runtime_checkable
class AuthAdapter(Protocol):
    async def authenticate(self, request: Request) -> AuthenticatedUser | None:
        ...


class AnonymousAuthAdapter:
    async def authenticate(self, request: Request) -> AuthenticatedUser | None:  # pragma: no cover - trivial
        return AuthenticatedUser(user_id="anonymous")


class PseudoAuthAdapter:
    def __init__(self, sessions: SessionStore) -> None:
        self._sessions = sessions

    async def authenticate(self, request: Request) -> AuthenticatedUser | None:
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if not token:
            return None
        ip = request.client.host if request.client else None
        session = self._sessions.resolve(
            token,
            user_agent=request.headers.get("user-agent"),
            ip_address=ip,
        )
        if session is None:
            return None
        display = session.email.split("@", 1)[0]
        return AuthenticatedUser(user_id=session.email, email_hash=session.email_hash, display_name=display)


AdapterFactory = Callable[[Config, SessionStore | None], AuthAdapter]


_REGISTRY: Dict[str, AdapterFactory] = {
    "none": lambda config, store: AnonymousAuthAdapter(),
    "pseudo": lambda config, store: PseudoAuthAdapter(_require_session_store(store)),
}


def register_auth_adapter(name: str, factory: AdapterFactory) -> None:
    _REGISTRY[name] = factory


def resolve_auth_adapter(mode: str, *, config: Config, session_store: SessionStore | None) -> AuthAdapter:
    if mode == "external":
        if not config.auth.external_adapter:
            raise RuntimeError("External auth mode requires 'auth.external_adapter'")
        return _load_external_adapter(config.auth.external_adapter, config)
    factory = _REGISTRY.get(mode)
    if factory is None:
        factory = _REGISTRY["none"]
    adapter = factory(config, session_store)
    return adapter


def _load_external_adapter(path: str, config: Config) -> AuthAdapter:
    module_name, _, attr = path.partition(":")
    if not attr:
        module_name, attr = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    factory = getattr(module, attr)
    try:
        adapter = factory(config)
    except TypeError:
        adapter = factory()
    if not isinstance(adapter, AuthAdapter):
        raise TypeError("External adapter factory must return an AuthAdapter")
    return adapter


def _require_session_store(store: SessionStore | None) -> SessionStore:
    if store is None:
        raise RuntimeError("Pseudo auth requires a session store")
    return store


__all__ = [
    "AuthAdapter",
    "AuthenticatedUser",
    "register_auth_adapter",
    "resolve_auth_adapter",
    "PseudoAuthAdapter",
]
