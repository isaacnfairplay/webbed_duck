from __future__ import annotations

from typing import Mapping

from webbed_duck.server.preprocess import PreprocessContext


def add_prefix(params: Mapping[str, object], *, context: PreprocessContext, prefix: str, note: str | None = None):
    assert isinstance(context, PreprocessContext)
    assert context.options.get("prefix") == prefix
    updated = dict(params)
    value = str(updated.get("name", ""))
    updated["name"] = f"{prefix}{value}"
    if note is not None:
        updated["note"] = note
    return updated


def add_suffix(params: Mapping[str, object], context: PreprocessContext, suffix: str = ""):
    assert context.route.id
    updated = dict(params)
    updated["name"] = f"{updated.get('name', '')}{suffix}"
    return updated


def return_none(params: Mapping[str, object], **_options):
    return None


def uppercase_value(params: Mapping[str, object], *, field: str, context: PreprocessContext):
    updated = dict(params)
    if field in updated and isinstance(updated[field], str):
        updated[field] = updated[field].upper()
    return updated
