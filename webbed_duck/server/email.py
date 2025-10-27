from __future__ import annotations

import importlib
from typing import Callable, Sequence

EmailSender = Callable[[Sequence[str], str, str, str | None, Sequence[tuple[str, bytes]] | None], None]


def load_email_sender(path: str | None) -> EmailSender | None:
    """Resolve ``path`` to a callable email sender.

    The adapter path supports either ``module:callable`` or dotted
    ``module.attr`` forms. When ``path`` is falsy ``None`` is returned.
    """

    if not path:
        return None
    module_name, _, attr = path.partition(":")
    if not attr:
        module_name, attr = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    sender = getattr(module, attr)
    if not callable(sender):
        raise TypeError("Email adapter must be callable")
    return sender


__all__ = ["EmailSender", "load_email_sender"]
