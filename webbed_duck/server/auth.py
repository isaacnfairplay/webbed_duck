from __future__ import annotations

import hashlib
import ipaddress
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from importlib import import_module
from typing import Callable, Dict, Mapping, Protocol, runtime_checkable

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from ..config import Config


SESSION_COOKIE = "wd_session"


@dataclass(slots=True)
class AuthenticatedUser:
    user_id: str
    email: str | None = None
    email_hash: str | None = None
    display_name: str | None = None


@dataclass(slots=True)
class SessionRecord:
    session_id: str
    user_id: str
    email: str
    email_hash: str
    display_name: str | None
    created_at: float
    expires_at: float
    user_agent: str | None
    ip_prefix: str | None


class SessionStore:
    """Persist pseudo-auth sessions in SQLite under ``storage_root``."""

    def __init__(self, storage_root: Path) -> None:
        self._path = Path(storage_root) / "runtime" / "meta.sqlite3"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_schema()

    def create_session(
        self,
        *,
        email: str,
        display_name: str | None,
        ttl_minutes: int,
        remember_me: bool,
        remember_days: int,
        user_agent: str | None,
        ip_address: str | None,
    ) -> SessionRecord:
        normalized = email.strip().lower()
        if "@" not in normalized:
            raise ValueError("Email address is required for pseudo auth")
        email_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        user_id = email_hash[:16]
        now = time.time()
        ttl_seconds = max(60, int(ttl_minutes) * 60)
        if remember_me and remember_days > 0:
            ttl_seconds = max(ttl_seconds, int(remember_days) * 24 * 60 * 60)
        expires_at = now + ttl_seconds
        session_id = secrets.token_urlsafe(32)
        prefix = _ip_prefix(ip_address)
        agent = (user_agent or "")[:256] or None

        with self._lock:
            with self._connect() as con:
                con.execute(
                    """
                    INSERT INTO sessions (
                        session_id, user_id, email, email_hash, display_name,
                        created_at, expires_at, user_agent, ip_prefix
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, user_id, normalized, email_hash, display_name, now, expires_at, agent, prefix),
                )
        return SessionRecord(
            session_id=session_id,
            user_id=user_id,
            email=normalized,
            email_hash=email_hash,
            display_name=display_name,
            created_at=now,
            expires_at=expires_at,
            user_agent=agent,
            ip_prefix=prefix,
        )

    def get_session(
        self,
        session_id: str,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> SessionRecord | None:
        with self._lock:
            with self._connect() as con:
                row = con.execute(
                    "SELECT session_id, user_id, email, email_hash, display_name, created_at, expires_at, user_agent, ip_prefix"
                    " FROM sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
        if row is None:
            return None
        record = SessionRecord(*row)
        now = time.time()
        if record.expires_at <= now:
            self.delete_session(session_id)
            return None
        if record.user_agent and user_agent and record.user_agent != user_agent[:256]:
            self.delete_session(session_id)
            return None
        prefix = _ip_prefix(ip_address)
        if record.ip_prefix and prefix and record.ip_prefix != prefix:
            self.delete_session(session_id)
            return None
        return record

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            with self._connect() as con:
                con.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def prune_expired(self) -> None:
        now = time.time()
        with self._lock:
            with self._connect() as con:
                con.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._path, isolation_level=None, check_same_thread=False)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self._path, isolation_level=None, check_same_thread=False) as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    email_hash TEXT NOT NULL,
                    display_name TEXT,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    user_agent TEXT,
                    ip_prefix TEXT
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")


def _ip_prefix(address: str | None) -> str | None:
    if not address:
        return None
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv4Address):
        parts = address.split(".")
        return ".".join(parts[:3]) if len(parts) >= 3 else address
    hextets = ip.exploded.split(":")
    return ":".join(hextets[:4])


@runtime_checkable
class AuthAdapter(Protocol):
    async def authenticate(self, request: Request) -> AuthenticatedUser | None:
        ...

    def register_routes(self, app: FastAPI) -> None:
        ...


class AnonymousAuthAdapter:
    def __init__(self) -> None:
        self._user = AuthenticatedUser(user_id="anonymous")

    async def authenticate(self, request: Request) -> AuthenticatedUser | None:  # pragma: no cover - trivial
        return self._user

    def register_routes(self, app: FastAPI) -> None:  # pragma: no cover - anonymous mode exposes nothing
        return None


class PseudoAuthAdapter:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._store = SessionStore(config.server.storage_root)
        self._allowed_domains = {item.lower() for item in config.auth.allowed_domains}

    async def authenticate(self, request: Request) -> AuthenticatedUser | None:
        session_id = request.cookies.get(SESSION_COOKIE)
        if not session_id:
            return None
        record = self._store.get_session(
            session_id,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        if record is None:
            return None
        return AuthenticatedUser(
            user_id=record.user_id,
            email=record.email,
            email_hash=record.email_hash,
            display_name=record.display_name,
        )

    def register_routes(self, app: FastAPI) -> None:
        @app.post("/auth/pseudo/login")
        async def login(
            request: Request,
            payload: Mapping[str, object] = Body(..., embed=False),
        ) -> JSONResponse:
            email_raw = str(payload.get("email", "")).strip().lower()
            if not email_raw or "@" not in email_raw:
                raise HTTPException(status_code=400, detail={"code": "invalid_email", "message": "Email is required"})
            if self._allowed_domains:
                domain = email_raw.split("@")[-1]
                if domain.lower() not in self._allowed_domains:
                    raise HTTPException(status_code=403, detail={"code": "domain_not_allowed", "message": "Email domain is not allowed"})
            display_name = payload.get("display_name")
            if display_name is not None:
                display_name = str(display_name).strip() or None
            remember_me = bool(payload.get("remember_me", False))
            record = self._store.create_session(
                email=email_raw,
                display_name=display_name,
                ttl_minutes=self._config.auth.session_ttl_minutes,
                remember_me=remember_me,
                remember_days=self._config.auth.remember_me_days,
                user_agent=request.headers.get("user-agent"),
                ip_address=request.client.host if request.client else None,
            )
            self._store.prune_expired()
            response = JSONResponse(
                {
                    "user": {
                        "user_id": record.user_id,
                        "email": record.email,
                        "email_hash": record.email_hash,
                        "display_name": record.display_name,
                    }
                }
            )
            max_age = max(60, int(record.expires_at - time.time()))
            response.set_cookie(
                SESSION_COOKIE,
                record.session_id,
                max_age=max_age,
                httponly=True,
                samesite="lax",
                secure=False,
            )
            return response

        @app.post("/auth/pseudo/logout")
        async def logout(request: Request) -> JSONResponse:
            session_id = request.cookies.get(SESSION_COOKIE)
            if session_id:
                self._store.delete_session(session_id)
            response = JSONResponse({"logged_out": True})
            response.delete_cookie(SESSION_COOKIE)
            return response

        @app.get("/auth/me")
        async def current_user(request: Request) -> JSONResponse:
            user = await self.authenticate(request)
            if user is None:
                raise HTTPException(status_code=401, detail={"code": "unauthenticated", "message": "Authentication required"})
            return JSONResponse(
                {
                    "user": {
                        "user_id": user.user_id,
                        "email": user.email,
                        "email_hash": user.email_hash,
                        "display_name": user.display_name,
                    }
                }
            )


class ProxyHeaderAuthAdapter:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._user_header = config.auth.proxy_header_user
        self._email_header = config.auth.proxy_header_email
        self._name_header = config.auth.proxy_header_name
        self._allowed_domains = {item.lower() for item in config.auth.allowed_domains}

    async def authenticate(self, request: Request) -> AuthenticatedUser | None:
        value = request.headers.get(self._user_header)
        if not value:
            return None
        user_id = value.strip()
        if not user_id:
            return None
        email_raw = request.headers.get(self._email_header)
        email_norm: str | None = None
        email_hash: str | None = None
        if email_raw:
            email_norm = email_raw.strip().lower()
            if self._allowed_domains:
                domain = email_norm.split("@")[-1]
                if domain not in self._allowed_domains:
                    raise HTTPException(status_code=403, detail={"code": "domain_not_allowed", "message": "Email domain is not allowed"})
            email_hash = hashlib.sha256(email_norm.encode("utf-8")).hexdigest()
        display_name = request.headers.get(self._name_header)
        if display_name:
            display_name = display_name.strip() or None
        return AuthenticatedUser(
            user_id=user_id,
            email=email_norm,
            email_hash=email_hash,
            display_name=display_name,
        )

    def register_routes(self, app: FastAPI) -> None:
        @app.get("/auth/proxy/ping")
        async def ping() -> Mapping[str, object]:  # pragma: no cover - simple readiness endpoint
            return {"proxy": True}


def _import_from_string(path: str):
    target = path
    if path.startswith("custom:"):
        target = path.split("custom:", 1)[1]
    if ":" in target:
        module_name, attribute = target.split(":", 1)
    else:
        module_name, attribute = target.rsplit(".", 1)
    module = import_module(module_name)
    return getattr(module, attribute)


def _load_external_adapter(config: Config) -> AuthAdapter:
    spec = config.auth.external_adapter
    if not spec:
        raise ValueError("auth.external_adapter must be configured for external mode")
    target = _import_from_string(spec)
    adapter = target
    if callable(target):
        try:
            candidate = target(config)
        except TypeError:
            candidate = target()
        adapter = candidate
    if not isinstance(adapter, AuthAdapter):
        raise TypeError("External adapter does not implement the AuthAdapter protocol")
    return adapter


_REGISTRY: Dict[str, Callable[[Config], AuthAdapter]] = {
    "none": lambda config: AnonymousAuthAdapter(),
    "pseudo": PseudoAuthAdapter,
    "proxy": ProxyHeaderAuthAdapter,
    "external": _load_external_adapter,
}

def register_auth_adapter(name: str, factory: Callable[[Config], AuthAdapter]) -> None:
    _REGISTRY[name] = factory


def resolve_auth_adapter(config: Config) -> AuthAdapter:
    factory = _REGISTRY.get(config.auth.mode, _REGISTRY["none"])
    adapter = factory(config)
    return adapter


__all__ = [
    "AuthAdapter",
    "AuthenticatedUser",
    "SESSION_COOKIE",
    "PseudoAuthAdapter",
    "ProxyHeaderAuthAdapter",
    "SessionStore",
    "register_auth_adapter",
    "resolve_auth_adapter",
]
