"""Invariant filter helpers for parameter widgets."""
from __future__ import annotations

from typing import Mapping, Sequence

from ..cache import (
    InvariantFilterSetting,
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


def _normalize_option_lookup(value: str, setting: InvariantFilterSetting) -> str:
    trimmed = value.strip()
    if not trimmed:
        return ""
    return trimmed.lower() if setting.case_insensitive else trimmed


def _tokens_for_values(
    values: Sequence[object],
    param_entry: Mapping[str, Mapping[str, object]],
    setting: InvariantFilterSetting,
) -> tuple[set[str], bool]:
    reverse_lookup: dict[str, str] = {}
    for token, entry in param_entry.items():
        if not isinstance(entry, Mapping):
            continue
        option_value = token_to_option_value(token, entry)
        normalized_option = _normalize_option_lookup(option_value, setting)
        if not normalized_option:
            continue
        reverse_lookup.setdefault(normalized_option, token)

    matched: set[str] = set()
    unknown = False
    for value in values:
        if value is None:
            lookup_value = _normalize_option_lookup("__null__", setting)
        elif isinstance(value, str):
            lookup_value = _normalize_option_lookup(value, setting)
        else:
            lookup_value = _normalize_option_lookup(str(value), setting)
        if not lookup_value:
            continue
        token = reverse_lookup.get(lookup_value)
        if token is None:
            unknown = True
            continue
        matched.add(token)
    return matched, unknown


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
        param_entry = index.get(param)
        if not isinstance(param_entry, Mapping):
            continue
        tokens, unknown = _tokens_for_values(normalized, param_entry, setting)
        if not tokens:
            if unknown:
                return set(), True
            continue
        token_pages: set[int] = set()
        for token in tokens:
            entry = param_entry.get(token)
            if not isinstance(entry, Mapping):
                unknown = True
                continue
            entry_pages = coerce_page_set(entry.get("pages"))
            if entry_pages is None:
                unknown = True
                continue
            token_pages.update(entry_pages)
        if not token_pages:
            return set(), True
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
        return "__null__"
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
