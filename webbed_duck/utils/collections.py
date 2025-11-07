"""Collection helpers used across the project."""
from __future__ import annotations

from typing import Callable, Hashable, Iterable, Iterator, MutableSequence, TypeVar, cast

T = TypeVar("T")


def unique_everseen(iterable: Iterable[T], *, key: Callable[[T], Hashable] | None = None) -> Iterator[T]:
    """Yield items from ``iterable`` while preserving their first occurrence order."""

    seen: set[Hashable] = set()
    for item in iterable:
        marker = key(item) if key is not None else cast(Hashable, item)
        if marker in seen:
            continue
        seen.add(marker)
        yield item


def extend_unique(
    target: MutableSequence[T],
    items: Iterable[T],
    *,
    key: Callable[[T], Hashable] | None = None,
    seen: set[Hashable] | None = None,
) -> MutableSequence[T]:
    """Extend ``target`` with deduplicated ``items`` using the provided ``key``."""

    markers = (
        seen
        if seen is not None
        else {key(item) if key is not None else cast(Hashable, item) for item in target}
    )
    for item in items:
        marker = key(item) if key is not None else cast(Hashable, item)
        if marker in markers:
            continue
        markers.add(marker)
        target.append(item)
    return target


__all__ = [
    "extend_unique",
    "unique_everseen",
]
