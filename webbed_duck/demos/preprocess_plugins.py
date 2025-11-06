from __future__ import annotations

from typing import Mapping

from webbed_duck.server.preprocess import PreprocessContext


def stamp_label(
    params: Mapping[str, object], *, context: PreprocessContext, label: str = "demo"
) -> Mapping[str, object]:
    """Attach a label string to the params mapping."""

    result = dict(params)
    result["label"] = label
    return result


def append_channel(
    params: Mapping[str, object], *, context: PreprocessContext, channel: str = "web"
) -> Mapping[str, object]:
    """Append a channel suffix to the ``name`` field if present."""

    result = dict(params)
    name = str(result.get("name", ""))
    if name:
        result["name"] = f"{name}-{channel}"
    else:
        result["name"] = channel
    return result
