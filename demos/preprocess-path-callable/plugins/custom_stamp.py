from __future__ import annotations

from typing import Mapping

from webbed_duck.server.preprocess import PreprocessContext


def derive_tag(
    params: Mapping[str, object], *, context: PreprocessContext, prefix: str = "path"
) -> Mapping[str, object]:
    """Attach a derived tag to demonstrate filesystem-based preprocessors."""

    result = dict(params)
    base = str(result.get("name", "")) or "anonymous"
    result["tag"] = f"{prefix}-{base}"
    return result
