"""Helpers for working with ISO-formatted date and datetime values."""

from __future__ import annotations

import datetime as _dt


def parse_iso_date(value: str) -> _dt.date:
    """Return a :class:`datetime.date` parsed from ``value``.

    ``value`` may contain surrounding whitespace. A :class:`ValueError` is raised
    when the payload cannot be interpreted as an ISO-8601 date.
    """

    text = value.strip()
    if not text:
        raise ValueError("empty string")
    return _dt.date.fromisoformat(text)


def parse_iso_datetime(value: str) -> _dt.datetime:
    """Return a :class:`datetime.datetime` parsed from ``value``.

    ``value`` may be a date (which will be combined with midnight) or a full
    ISO-8601 datetime. Trailing ``Z`` designators are mapped to ``+00:00`` to
    satisfy :func:`datetime.datetime.fromisoformat`.
    """

    text = value.strip()
    if not text:
        raise ValueError("empty string")
    if text[-1:] in {"Z", "z"}:
        text = text[:-1] + "+00:00"
    try:
        return _dt.datetime.fromisoformat(text)
    except ValueError as original_error:
        if "T" not in text and " " not in text:
            try:
                date_value = _dt.date.fromisoformat(text)
            except ValueError:
                raise original_error
            return _dt.datetime.combine(date_value, _dt.time())
        raise original_error


def isoformat_datetime(value: _dt.datetime) -> str:
    """Return a canonical ISO string for ``value``.

    When the datetime is timezone-aware and represents UTC the output uses the
    ``Z`` suffix for readability.
    """

    text = value.isoformat()
    tzinfo = value.tzinfo
    if tzinfo is not None:
        try:
            offset = value.utcoffset()
        except Exception:  # pragma: no cover - defensive guard
            offset = None
        if offset is not None and offset.total_seconds() == 0 and text.endswith("+00:00"):
            return text[:-6] + "Z"
    return text


__all__ = ["parse_iso_date", "parse_iso_datetime", "isoformat_datetime"]

