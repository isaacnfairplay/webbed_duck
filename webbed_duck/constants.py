"""Helpers for resolving compile-time constants from configuration and routes."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import keyring
from keyring.errors import KeyringError, NoKeyringError


class ConstantResolutionError(ValueError):
    """Raised when a constant cannot be resolved from configuration metadata."""


_ALLOWED_MAPPING_KEYS = {
    "value",
    "keyring",
    "secret",
    "service",
    "username",
    "keyring_service",
    "keyring_username",
}


def parse_constant_block(
    data: Mapping[str, Any] | None,
    *,
    context: str,
) -> dict[str, str]:
    """Return a mapping of constant names to string values.

    Parameters
    ----------
    data:
        Mapping loaded from TOML.
    context:
        Human-readable prefix describing the source (e.g. ``"server.constants"``).
    """

    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise ConstantResolutionError(
            f"{context} must be a table of string constants or keyring references"
        )

    constants: dict[str, str] = {}
    for raw_name, raw_value in data.items():
        name = str(raw_name)
        if name in constants:
            raise ConstantResolutionError(
                f"{context}.{name} is defined more than once; remove duplicates"
            )
        constants[name] = _resolve_constant_value(raw_value, context=f"{context}.{name}")
    return constants


def _resolve_constant_value(value: Any, *, context: str) -> str:
    if isinstance(value, Mapping):
        unexpected = set(value) - _ALLOWED_MAPPING_KEYS
        if unexpected:
            keys = ", ".join(sorted(unexpected))
            raise ConstantResolutionError(
                f"{context} contains unsupported keys: {keys}"
            )
        has_literal = "value" in value
        has_keyring = any(
            key in value
            for key in ("keyring", "secret", "service", "username", "keyring_service", "keyring_username")
        )
        if has_literal and has_keyring:
            raise ConstantResolutionError(
                f"{context} must specify either 'value' or keyring credentials, not both"
            )
        if has_literal:
            literal = value["value"]
            if not isinstance(literal, str):
                raise ConstantResolutionError(f"{context}.value must be a string literal")
            return literal
        service, username = _extract_keyring_identity(value, context=context)
        if service is None or username is None:
            raise ConstantResolutionError(
                f"{context} must define a string literal or keyring service/username"
            )
        return _load_keyring_secret(service, username, context=context)

    if isinstance(value, str):
        return value

    raise ConstantResolutionError(
        f"{context} must be a string literal or keyring reference"
    )


def _extract_keyring_identity(
    payload: Mapping[str, Any], *, context: str
) -> tuple[str | None, str | None]:
    direct = payload.get("keyring")
    if direct is None:
        direct = payload.get("secret")
    if direct is not None:
        return _interpret_keyring_payload(direct, context=context)

    service = payload.get("service") or payload.get("keyring_service")
    username = payload.get("username") or payload.get("keyring_username")
    if service is None and username is None:
        return None, None
    if not isinstance(service, str) or not isinstance(username, str):
        raise ConstantResolutionError(
            f"{context} keyring service and username must be strings"
        )
    return service, username


def _interpret_keyring_payload(payload: Any, *, context: str) -> tuple[str, str]:
    if isinstance(payload, Mapping):
        service = payload.get("service") or payload.get("keyring_service")
        username = payload.get("username") or payload.get("keyring_username")
        if not isinstance(service, str) or not isinstance(username, str):
            raise ConstantResolutionError(
                f"{context} keyring payload requires string service and username"
            )
        return service, username

    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        if len(payload) != 2:
            raise ConstantResolutionError(
                f"{context} keyring payload sequences must provide [service, username]"
            )
        service_raw, username_raw = payload
        if not isinstance(service_raw, str) or not isinstance(username_raw, str):
            raise ConstantResolutionError(
                f"{context} keyring payload requires string service and username"
            )
        return service_raw, username_raw

    text = str(payload)
    if ":" not in text:
        raise ConstantResolutionError(
            f"{context} keyring payload must be formatted as 'service:username'"
        )
    service, username = text.split(":", 1)
    service = service.strip()
    username = username.strip()
    if not service or not username:
        raise ConstantResolutionError(
            f"{context} keyring payload must include non-empty service and username"
        )
    return service, username


def _load_keyring_secret(service: str, username: str, *, context: str) -> str:
    try:
        secret = keyring.get_password(service, username)
    except NoKeyringError as exc:  # pragma: no cover - backend availability depends on environment
        raise ConstantResolutionError(
            f"{context} could not access a usable keyring backend: {exc}"
        ) from exc
    except KeyringError as exc:  # pragma: no cover - backend-specific failures
        raise ConstantResolutionError(
            f"{context} could not read keyring entry: {exc}"
        ) from exc

    if secret is None:
        raise ConstantResolutionError(
            f"{context} keyring entry not found for service={service!r} username={username!r}"
        )
    if not isinstance(secret, str):  # pragma: no cover - defensive
        raise ConstantResolutionError(
            f"{context} keyring returned a non-string secret"
        )
    return secret


__all__ = ["ConstantResolutionError", "parse_constant_block"]
