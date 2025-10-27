"""Session management helpers for pseudo authentication."""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..config import AuthConfig
from .meta import MetaStore, _utcnow, deserialize_datetime, serialize_datetime

SESSION_COOKIE_NAME = "wd_session"


@dataclass(slots=True)
class StoredSession:
    token: str
    email: str
    email_hash: str
    expires_at: datetime


class SessionStore:
    """Create and validate browser sessions bound to user agent and IP."""

    def __init__(self, store: MetaStore, config: AuthConfig) -> None:
        self._store = store
        self._config = config
        self._allowed_domains = {item.lower() for item in config.allowed_domains}

    def create(
        self,
        *,
        email: str,
        user_agent: str | None,
        ip_address: str | None,
        remember_me: bool,
    ) -> StoredSession:
        email_norm = email.strip().lower()
        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        email_hash = _hash_token(email_norm)
        ttl_minutes = self._config.session_ttl_minutes
        if remember_me:
            ttl_minutes = max(ttl_minutes, self._config.remember_me_days * 24 * 60)
        now = _utcnow()
        expires = now + timedelta(minutes=ttl_minutes)
        user_agent_hash = _hash_text(user_agent) if user_agent else None
        ip_prefix = _ip_prefix(ip_address) if ip_address else None
        with self._store.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sessions (
                    token_hash, email, email_hash, created_at, expires_at, user_agent_hash, ip_prefix
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token_hash,
                    email_norm,
                    email_hash,
                    serialize_datetime(now),
                    serialize_datetime(expires),
                    user_agent_hash,
                    ip_prefix,
                ),
            )
            conn.commit()
        return StoredSession(token=token, email=email_norm, email_hash=email_hash, expires_at=expires)

    def resolve(
        self,
        token: str,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> StoredSession | None:
        token_hash = _hash_token(token)
        user_agent_hash = _hash_text(user_agent) if user_agent else None
        ip_prefix = _ip_prefix(ip_address) if ip_address else None
        with self._store.connect() as conn:
            row = conn.execute(
                "SELECT email, email_hash, expires_at, user_agent_hash, ip_prefix FROM sessions WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            expires_at = deserialize_datetime(row["expires_at"])
            if expires_at <= _utcnow():
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
                conn.commit()
                return None
            if row["user_agent_hash"] and user_agent_hash and row["user_agent_hash"] != user_agent_hash:
                return None
            if row["ip_prefix"] and ip_prefix and row["ip_prefix"] != ip_prefix:
                return None
            if row["user_agent_hash"] and user_agent_hash is None:
                return None
            if row["ip_prefix"] and ip_prefix is None:
                return None
        return StoredSession(token=token, email=row["email"], email_hash=row["email_hash"], expires_at=expires_at)

    def destroy(self, token: str) -> None:
        token_hash = _hash_token(token)
        with self._store.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            conn.commit()

    def validate_email(self, email: str) -> str:
        email_norm = email.strip().lower()
        if not email_norm or "@" not in email_norm:
            raise ValueError("Email address is required")
        if self._allowed_domains:
            domain = email_norm.split("@", 1)[1]
            if domain not in self._allowed_domains:
                raise ValueError("Email domain is not allowed")
        return email_norm


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_text(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ip_prefix(ip: str) -> str:
    if ":" in ip:
        parts = ip.split(":")
        return ":".join(parts[:4])
    octets = ip.split(".")
    if len(octets) >= 3:
        return ".".join(octets[:3])
    return ip


__all__ = ["SessionStore", "StoredSession", "SESSION_COOKIE_NAME"]
