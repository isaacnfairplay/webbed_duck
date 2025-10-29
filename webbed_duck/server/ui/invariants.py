"""Invariant filter helpers for parameter widgets."""
from __future__ import annotations

from typing import Mapping, Sequence

from ..cache import (
    InvariantFilterSetting,
    canonicalize_invariant_value,
    normalize_invariant_value,
    parse_invariant_filters,
)


def extract_invariant_settings(
    route_metadata: Mapping[str, object] | None,
    cache_meta: Mapping[str, object] | None,
) -> dict[str, InvariantFilterSetting]:
    """Return invariant filter settings for the current route."""

    settings: dict[str, InvariantFilterSetting] = {}
    if isinstance(route_metadata, Mapping):
        cache_block = route_metadata.get("cache")
        if isinstance(cache_block, Mapping):
            raw_filters = cache_block.get("invariant_filters")
            for setting in parse_invariant_filters(raw_filters):
                settings[setting.param] = setting
    if settings:
        return settings
    index = coerce_invariant_index(cache_meta)
    if not index:
        return settings
    for param in index.keys():
        if param not in settings:
            settings[param] = InvariantFilterSetting(param=param, column=str(param))
    return settings


def coerce_invariant_index(
    cache_meta: Mapping[str, object] | None,
) -> Mapping[str, Mapping[str, Mapping[str, object]]] | None:
    if not isinstance(cache_meta, Mapping):
        return None
    index = cache_meta.get("invariant_index")
    if isinstance(index, Mapping):
        return index  # type: ignore[return-value]
    return None


def pages_for_other_invariants(
    target_param: str,
    invariant_settings: Mapping[str, InvariantFilterSetting],
    index: Mapping[str, Mapping[str, Mapping[str, object]]],
    current_values: Mapping[str, object],
) -> tuple[set[int] | None, bool]:
    pages: set[int] | None = None
    filters_applied = False
    for param, setting in invariant_settings.items():
        if param == target_param:
            continue
        raw_value = current_values.get(param)
        normalized_raw = normalize_invariant_value(raw_value, setting)
        normalized = [
            value
            for value in normalized_raw
            if not (isinstance(value, str) and value == "")
        ]
        if not normalized:
            continue
        filters_applied = True
        tokens = {
            canonicalize_invariant_value(value, setting)
            for value in normalized
        }
        if not tokens:
            continue
        param_entry = index.get(param)
        if not isinstance(param_entry, Mapping):
            continue
        token_pages: set[int] = set()
        unknown = False
        for token in tokens:
            entry = param_entry.get(token)
            if not isinstance(entry, Mapping):
                continue
            entry_pages = coerce_page_set(entry.get("pages"))
            if entry_pages is None:
                unknown = True
                continue
            token_pages.update(entry_pages)
        if not token_pages and not unknown:
            return set(), True
        if not token_pages and unknown:
            continue
        if pages is None:
            pages = token_pages
        else:
            pages &= token_pages
        if pages is not None and not pages:
            return set(), True
    return pages, filters_applied


def coerce_page_set(pages: object) -> set[int] | None:
    if not isinstance(pages, Sequence):
        return None
    result: set[int] = set()
    for page in pages:
        try:
            result.add(int(page))
        except (TypeError, ValueError):
            continue
    return result or None


def token_to_option_value(token: str, entry: Mapping[str, object]) -> str:
    sample = entry.get("sample")
    sample_text = str(sample) if isinstance(sample, str) else None
    if token == "__null__":
        return ""
    prefix, _, payload = token.partition(":")
    if prefix == "str":
        return sample_text if sample_text is not None else payload
    if prefix in {"bool", "num", "datetime", "bytes"} and payload:
        return payload
    return sample_text if sample_text is not None else token


def token_to_option_label(token: str, entry: Mapping[str, object]) -> str:
    sample = entry.get("sample")
    if isinstance(sample, str) and sample:
        return sample
    if token == "__null__":
        return "(null)"
    if token.startswith("str:"):
        return "(blank)"
    prefix, _, payload = token.partition(":")
    return payload or token


__all__ = [
    "extract_invariant_settings",
    "coerce_invariant_index",
    "pages_for_other_invariants",
    "coerce_page_set",
    "token_to_option_value",
    "token_to_option_label",
]
