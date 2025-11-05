"""Helpers for resolving constant substitutions for SQL compilation."""
from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any, Callable, Dict

try:  # pragma: no cover - import guard for environments missing keyring
    import keyring
    from keyring.errors import KeyringError
except ModuleNotFoundError:  # pragma: no cover - allow keyring-less environments to surface clean errors
    keyring = None  # type: ignore[assignment]
    KeyringError = Exception  # type: ignore[assignment]


_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def resolve_constant_table(
    raw: Mapping[str, Any],
    *,
    error_cls: type[Exception],
    source: str,
    secret_getter: Callable[[str, str], str | None] | None = None,
) -> Dict[str, str]:
    """Resolve ``raw`` constant definitions into a mapping of string values."""

    if secret_getter is None:
        if keyring is None:  # pragma: no cover - defensive fallback when dependency missing
            def _missing_secret_getter(service: str, username: str) -> str | None:
                raise error_cls(
                    "keyring dependency is required to resolve secrets but is not available"
                )

            secret_getter = _missing_secret_getter
        else:
            secret_getter = keyring.get_password

    resolved: Dict[str, str] = {}
    for raw_name, raw_value in raw.items():
        if not isinstance(raw_name, str):
            raise error_cls(f"Constant names must be strings in {source}")
        name = raw_name.strip()
        if not name:
            raise error_cls(f"Constant names cannot be empty in {source}")
        if not _NAME_PATTERN.match(name):
            raise error_cls(
                f"Invalid constant name '{name}' in {source}; use letters, numbers, and underscores"
            )
        resolved[name] = _resolve_constant_value(
            name,
            raw_value,
            error_cls=error_cls,
            source=source,
            secret_getter=secret_getter,
        )
    return resolved


def _resolve_constant_value(
    name: str,
    value: Any,
    *,
    error_cls: type[Exception],
    source: str,
    secret_getter: Callable[[str, str], str | None],
) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        lowered: Dict[str, Any] = {str(key).lower(): item for key, item in value.items()}
        if "value" in lowered:
            return str(lowered["value"])
        if "literal" in lowered:
            return str(lowered["literal"])
        secret_spec: Any | None = None
        if "secret" in lowered:
            secret_spec = lowered["secret"]
        elif "keyring" in lowered:
            secret_spec = lowered["keyring"]
        if secret_spec is None:
            raise error_cls(
                f"Constant '{name}' in {source} must specify 'value' or 'secret'"
            )
        service, username = _parse_secret_spec(
            secret_spec, name=name, error_cls=error_cls, source=source
        )
        try:
            secret = secret_getter(service, username)
        except KeyringError as exc:  # pragma: no cover - backend specific errors
            raise error_cls(
                f"Failed to read keyring secret for constant '{name}' in {source}: {exc}"
            ) from exc
        if secret is None:
            raise error_cls(
                f"Secret for constant '{name}' not found in keyring (service={service!r}, username={username!r})"
            )
        return secret
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8")
    return str(value)


def _parse_secret_spec(
    spec: Any,
    *,
    name: str,
    error_cls: type[Exception],
    source: str,
) -> tuple[str, str]:
    if isinstance(spec, Mapping):
        lowered: Dict[str, Any] = {str(key).lower(): item for key, item in spec.items()}
        service = lowered.get("service") or lowered.get("name")
        username = (
            lowered.get("username")
            or lowered.get("user")
            or lowered.get("account")
            or lowered.get("key")
        )
        if not service or not username:
            raise error_cls(
                f"Constant '{name}' in {source} secret must include 'service' and 'username'"
            )
        return str(service), str(username)

    text = str(spec).strip()
    for separator in (":", "/"):
        if separator in text:
            left, right = text.split(separator, 1)
            service = left.strip()
            username = right.strip()
            if service and username:
                return service, username
    raise error_cls(
        f"Constant '{name}' in {source} secret must specify service and username"
    )


__all__ = ["resolve_constant_table"]
