"""Share token creation and lookup helpers."""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Mapping, Sequence

from fastapi import Request

from ..config import Config
from .meta import MetaStore, ShareRecord, _utcnow, deserialize_datetime, serialize_datetime


@dataclass(slots=True)
class CreatedShare:
    token: str
    route_id: str
    format: str
    expires_at: datetime
    params: Mapping[str, object]


class ShareStore:
    def __init__(self, meta: MetaStore, config: Config) -> None:
        self._meta = meta
        self._config = config

    def create(
        self,
        route_id: str,
        *,
        params: Mapping[str, object],
        fmt: str,
        created_by_hash: str | None,
        request: Request,
    ) -> CreatedShare:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        ttl = timedelta(minutes=self._config.email.share_token_ttl_minutes)
        now = _utcnow()
        expires_at = now + ttl
        user_agent_hash = _hash_text(request.headers.get("user-agent")) if self._config.email.bind_share_to_user_agent else None
        ip_prefix = _ip_prefix(request.client.host if request.client else None) if self._config.email.bind_share_to_ip_prefix else None
        params_json = json.dumps(params, sort_keys=True)
        with self._meta.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO shares (
                    token_hash, route_id, params_json, format, created_at, expires_at, created_by_hash, user_agent_hash, ip_prefix
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token_hash,
                    route_id,
                    params_json,
                    fmt,
                    serialize_datetime(now),
                    serialize_datetime(expires_at),
                    created_by_hash,
                    user_agent_hash,
                    ip_prefix,
                ),
            )
            conn.commit()
        return CreatedShare(token=token, route_id=route_id, format=fmt, expires_at=expires_at, params=params)

    def resolve(self, token: str, request: Request) -> ShareRecord | None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        ua_hash = _hash_text(request.headers.get("user-agent")) if self._config.email.bind_share_to_user_agent else None
        ip_prefix = _ip_prefix(request.client.host if request.client else None) if self._config.email.bind_share_to_ip_prefix else None
        with self._meta.connect() as conn:
            row = conn.execute(
                "SELECT route_id, params_json, format, expires_at, user_agent_hash, ip_prefix FROM shares WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            expires_at = deserialize_datetime(row["expires_at"])
            if expires_at <= _utcnow():
                conn.execute("DELETE FROM shares WHERE token_hash = ?", (token_hash,))
                conn.commit()
                return None
            if row["user_agent_hash"] and ua_hash and row["user_agent_hash"] != ua_hash:
                return None
            if row["ip_prefix"] and ip_prefix and row["ip_prefix"] != ip_prefix:
                return None
            if row["user_agent_hash"] and ua_hash is None:
                return None
            if row["ip_prefix"] and ip_prefix is None:
                return None
            params = json.loads(row["params_json"])
        return ShareRecord(
            route_id=row["route_id"],
            params=params,
            format=row["format"],
            expires_at=expires_at,
        )


def _hash_text(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ip_prefix(ip: str | None) -> str | None:
    if not ip:
        return None
    if ":" in ip:
        parts = ip.split(":")
        return ":".join(parts[:4])
    octets = ip.split(".")
    if len(octets) >= 3:
        return ".".join(octets[:3])
    return ip


__all__ = ["ShareStore", "CreatedShare"]
