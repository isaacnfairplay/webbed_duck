"""Server runtime helpers."""

from __future__ import annotations

import sys


def preferred_uvicorn_http_implementation() -> str:
    """Return the HTTP implementation Uvicorn should use.

    Uvicorn defaults to ``"auto"`` which prefers the ``httptools`` parser when it
    is importable.  The ``httptools`` project has not published wheels for
    CPython 3.13 on Windows yet, which results in an importable module that lacks
    the ``HttpRequestParser`` attribute.  When that happens Uvicorn crashes when
    it instantiates the protocol class (see ``uvicorn.protocols.http``).

    Until upstream ships compatible wheels we proactively force the pure Python
    ``h11`` implementation on the affected platforms.  Other environments keep
    the default "auto" behaviour so Linux/macOS installations continue to take
    advantage of ``httptools`` when available.
    """

    if sys.platform.startswith("win") and sys.version_info >= (3, 13):
        return "h11"
    return "auto"


__all__ = ["preferred_uvicorn_http_implementation"]
