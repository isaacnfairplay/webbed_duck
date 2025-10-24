"""Helpers for exercising external auth adapters in tests."""

from __future__ import annotations

import hashlib
from fastapi import FastAPI, Request

from webbed_duck.server.auth import AuthAdapter, AuthenticatedUser


class StaticExternalAuthAdapter:
    def __init__(self, config) -> None:
        email = "external@example.com"
        self._user = AuthenticatedUser(
            user_id="external-user",
            email=email,
            email_hash=hashlib.sha256(email.encode("utf-8")).hexdigest(),
            display_name="External User",
        )

    async def authenticate(self, request: Request) -> AuthenticatedUser | None:  # pragma: no cover - deterministic
        return self._user

    def register_routes(self, app: FastAPI) -> None:
        @app.get("/auth/external/ping")
        async def ping() -> dict[str, bool]:  # pragma: no cover - trivial
            return {"external": True}


def create_adapter(config) -> AuthAdapter:
    return StaticExternalAuthAdapter(config)
