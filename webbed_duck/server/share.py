"""Share token creation and lookup helpers."""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Sequence

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
    redact_columns: Sequence[str]


@dataclass(slots=True)
class _ShareBindings:
    user_agent_hash: str | None
    ip_prefix: str | None


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
        redact_columns: Sequence[str],
        created_by_hash: str | None,
        request: Request,
    ) -> CreatedShare:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        ttl = timedelta(minutes=self._config.email.share_token_ttl_minutes)
        now = _utcnow()
        expires_at = now + ttl
        bindings = _extract_bindings(self._config, request)
        params_json = json.dumps(params, sort_keys=True)
        stored_redactions, redact_json = _prepare_redactions(redact_columns)
        with self._meta.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO shares (
                    token_hash, route_id, params_json, format, created_at, expires_at, created_by_hash, user_agent_hash, ip_prefix, redact_columns_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token_hash,
                    route_id,
                    params_json,
                    fmt,
                    serialize_datetime(now),
                    serialize_datetime(expires_at),
                    created_by_hash,
                    bindings.user_agent_hash,
                    bindings.ip_prefix,
                    redact_json,
                ),
            )
            conn.commit()
        return CreatedShare(
            token=token,
            route_id=route_id,
            format=fmt,
            expires_at=expires_at,
            params=params,
            redact_columns=stored_redactions,
        )

    def resolve(self, token: str, request: Request) -> ShareRecord | None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        bindings = _extract_bindings(self._config, request)
        with self._meta.connect() as conn:
            row = conn.execute(
                """
                SELECT route_id, params_json, format, expires_at, user_agent_hash, ip_prefix, redact_columns_json
                FROM shares
                WHERE token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            expires_at = deserialize_datetime(row["expires_at"])
            if expires_at <= _utcnow():
                conn.execute("DELETE FROM shares WHERE token_hash = ?", (token_hash,))
                conn.commit()
                return None
            stored_bindings = _ShareBindings(
                user_agent_hash=row["user_agent_hash"],
                ip_prefix=row["ip_prefix"],
            )
            if not _bindings_match(stored_bindings, bindings):
                return None
            params = json.loads(row["params_json"])
            redact_columns = _parse_redactions(row["redact_columns_json"])
        return ShareRecord(
            route_id=row["route_id"],
            params=params,
            format=row["format"],
            expires_at=expires_at,
            redact_columns=redact_columns,
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


def _extract_bindings(config: Config, request: Request) -> _ShareBindings:
    user_agent_hash = None
    if config.email.bind_share_to_user_agent:
        user_agent_hash = _hash_text(request.headers.get("user-agent"))
    ip_prefix = None
    if config.email.bind_share_to_ip_prefix:
        ip_prefix = _ip_prefix(request.client.host if request.client else None)
    return _ShareBindings(user_agent_hash=user_agent_hash, ip_prefix=ip_prefix)


def _bindings_match(stored: _ShareBindings, provided: _ShareBindings) -> bool:
    if stored.user_agent_hash:
        if provided.user_agent_hash is None:
            return False
        if stored.user_agent_hash != provided.user_agent_hash:
            return False
    if stored.ip_prefix:
        if provided.ip_prefix is None:
            return False
        if stored.ip_prefix != provided.ip_prefix:
            return False
    return True


def _prepare_redactions(values: Sequence[str]) -> tuple[tuple[str, ...], str | None]:
    normalized = tuple(sorted({str(name) for name in values}))
    if not normalized:
        return (), None
    return normalized, json.dumps(list(normalized))


def _parse_redactions(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if isinstance(loaded, list):
        return tuple(sorted({str(item) for item in loaded}))
    return ()


__all__ = ["ShareStore", "CreatedShare"]
