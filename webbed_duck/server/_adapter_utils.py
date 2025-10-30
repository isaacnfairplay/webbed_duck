from __future__ import annotations

def normalize_adapter_path(path: str | None, *, optional: bool) -> tuple[str, str] | None:
    """Normalize ``path`` to ``(module, attribute)`` with whitespace trimmed.

    When ``optional`` is ``True`` and ``path`` is ``None`` or blank, ``None`` is
    returned. Otherwise the path must include a module and attribute separated by
    ``:`` or ``.``. Whitespace around both tokens is ignored. ``ValueError`` is
    raised when the format is invalid.
    """

    if path is None:
        if optional:
            return None
        raise ValueError("Adapter path must not be empty")

    trimmed = path.strip()
    if not trimmed:
        if optional:
            return None
        raise ValueError("Adapter path must not be empty")

    module_part: str
    attr_part: str
    if ":" in trimmed:
        module_part, attr_part = trimmed.split(":", 1)
    else:
        if "." not in trimmed:
            raise ValueError("Adapter path must include a callable name")
        module_part, attr_part = trimmed.rsplit(".", 1)

    module_name = module_part.strip()
    attr_name = attr_part.strip()
    if not module_name or not attr_name:
        raise ValueError("Adapter path must include both module and attribute names")

    return module_name, attr_name


__all__ = ["normalize_adapter_path"]
