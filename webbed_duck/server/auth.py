from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Protocol, runtime_checkable

from fastapi import Request


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


_REGISTRY: Dict[str, Callable[[], AuthAdapter]] = {
    "none": AnonymousAuthAdapter,
}


def register_auth_adapter(name: str, factory: Callable[[], AuthAdapter]) -> None:
    _REGISTRY[name] = factory


def resolve_auth_adapter(mode: str) -> AuthAdapter:
    factory = _REGISTRY.get(mode)
    if factory is None:
        factory = AnonymousAuthAdapter
    adapter = factory()
    return adapter


__all__ = ["AuthAdapter", "AuthenticatedUser", "register_auth_adapter", "resolve_auth_adapter"]
