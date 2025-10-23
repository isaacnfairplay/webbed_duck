"""SQLite-backed share token store with binding safeguards."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(slots=True)
class ShareToken:
    token: str
    expires_at: float


@dataclass(slots=True)
class ShareRecord:
    route_id: str
    params: Mapping[str, object]
    payload: Mapping[str, object]
    expires_at: float
    bind_user_agent: bool
    bind_ip_prefix: bool
    bound_user_agent: str | None
    bound_ip_prefix: str | None
    uses: int
    max_uses: int


class ShareError(RuntimeError):
    """Raised when a share token cannot be redeemed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ShareStore:
    """Persist share tokens with hashing, TTL and binding controls."""

    def __init__(self, storage_root: Path) -> None:
        self._path = Path(storage_root) / "runtime" / "meta.sqlite3"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_schema()

    def create_share(
        self,
        *,
        route_id: str,
        params: Mapping[str, object],
        payload: Mapping[str, object],
        ttl_minutes: int,
        bind_user_agent: bool,
        bind_ip_prefix: bool,
        user_agent: str | None,
        ip_address: str | None,
        owner_user_id: str | None,
        owner_email_hash: str | None,
        max_uses: int = 1,
    ) -> ShareToken:
        now = time.time()
        ttl_seconds = max(60, int(ttl_minutes) * 60)
        expires_at = now + ttl_seconds
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        params_json = json.dumps(params, sort_keys=True)
        payload_json = json.dumps(payload)
        agent = (user_agent or "")[:256] if bind_user_agent and user_agent else None
        prefix = _ip_prefix(ip_address) if bind_ip_prefix else None
        uses_allowed = max(1, int(max_uses))

        with self._lock:
            with self._connect() as con:
                con.execute(
                    """
                    INSERT INTO shares (
                        token_hash, route_id, params_json, payload_json, created_at, expires_at,
                        bind_user_agent, bind_ip_prefix, bound_user_agent, bound_ip_prefix,
                        uses, max_uses, owner_user_id, owner_email_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (
                        token_hash,
                        route_id,
                        params_json,
                        payload_json,
                        now,
                        expires_at,
                        1 if bind_user_agent else 0,
                        1 if bind_ip_prefix else 0,
                        agent,
                        prefix,
                        uses_allowed,
                        owner_user_id,
                        owner_email_hash,
                    ),
                )
        return ShareToken(token=token, expires_at=expires_at)

    def consume_share(
        self,
        token: str,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> ShareRecord:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.time()
        with self._lock:
            with self._connect() as con:
                row = con.execute(
                    """
                    SELECT route_id, params_json, payload_json, expires_at,
                           bind_user_agent, bind_ip_prefix,
                           bound_user_agent, bound_ip_prefix,
                           uses, max_uses
                    FROM shares WHERE token_hash = ?
                    """,
                    (token_hash,),
                ).fetchone()
                if row is None:
                    raise ShareError("invalid_token", "Share token is invalid or expired")

                (
                    route_id,
                    params_json,
                    payload_json,
                    expires_at,
                    bind_user_agent,
                    bind_ip_prefix,
                    bound_user_agent,
                    bound_ip_prefix,
                    uses,
                    max_uses,
                ) = row

                if expires_at <= now:
                    con.execute("DELETE FROM shares WHERE token_hash = ?", (token_hash,))
                    raise ShareError("share_expired", "Share link has expired")
                if uses >= max_uses:
                    con.execute("DELETE FROM shares WHERE token_hash = ?", (token_hash,))
                    raise ShareError("share_used", "Share link was already used")

                updates: list[tuple[str, object]] = []
                truncated_agent = (user_agent or "")[:256] or None
                if bind_user_agent:
                    if truncated_agent is None:
                        raise ShareError("user_agent_required", "Share link requires a User-Agent header")
                    if bound_user_agent is None:
                        bound_user_agent = truncated_agent
                        updates.append(("bound_user_agent", truncated_agent))
                    elif bound_user_agent != truncated_agent:
                        raise ShareError("user_agent_mismatch", "Share link is bound to a different device")

                prefix = _ip_prefix(ip_address) if (bind_ip_prefix or bound_ip_prefix) else None
                if bind_ip_prefix:
                    if prefix is None:
                        raise ShareError("ip_required", "Share link requires a routable client IP")
                    if bound_ip_prefix is None:
                        bound_ip_prefix = prefix
                        updates.append(("bound_ip_prefix", prefix))
                    elif bound_ip_prefix != prefix:
                        raise ShareError("ip_mismatch", "Share link is bound to a different network segment")

                uses += 1
                updates.append(("uses", uses))
                updates.append(("used_at", now))

                if updates:
                    columns = ", ".join(f"{name} = ?" for name, _ in updates)
                    values = [value for _, value in updates]
                    values.append(token_hash)
                    con.execute(f"UPDATE shares SET {columns} WHERE token_hash = ?", values)

                if uses >= max_uses:
                    con.execute("DELETE FROM shares WHERE token_hash = ?", (token_hash,))

        return ShareRecord(
            route_id=route_id,
            params=json.loads(params_json),
            payload=json.loads(payload_json),
            expires_at=expires_at,
            bind_user_agent=bool(bind_user_agent),
            bind_ip_prefix=bool(bind_ip_prefix),
            bound_user_agent=bound_user_agent,
            bound_ip_prefix=bound_ip_prefix,
            uses=uses,
            max_uses=max_uses,
        )

    def prune_expired(self) -> None:
        now = time.time()
        with self._lock:
            with self._connect() as con:
                con.execute("DELETE FROM shares WHERE expires_at <= ?", (now,))

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._path, isolation_level=None, check_same_thread=False)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self._path, isolation_level=None, check_same_thread=False) as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS shares (
                    token_hash TEXT PRIMARY KEY,
                    route_id TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    bind_user_agent INTEGER NOT NULL,
                    bind_ip_prefix INTEGER NOT NULL,
                    bound_user_agent TEXT,
                    bound_ip_prefix TEXT,
                    used_at REAL,
                    uses INTEGER NOT NULL DEFAULT 0,
                    max_uses INTEGER NOT NULL,
                    owner_user_id TEXT,
                    owner_email_hash TEXT
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_shares_route ON shares(route_id)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_shares_expiry ON shares(expires_at)")


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


__all__ = ["ShareStore", "ShareToken", "ShareRecord", "ShareError"]
