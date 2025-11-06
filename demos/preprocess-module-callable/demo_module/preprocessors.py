from __future__ import annotations

from datetime import datetime
from typing import Mapping

from webbed_duck.server.preprocess import PreprocessContext


def module_greeting(
    params: Mapping[str, object],
    *,
    context: PreprocessContext,
    prefix: str = "module",
) -> Mapping[str, object]:
    """Inject a greeting and timestamp to prove the module-based preprocessor ran."""

    name = str(params.get("name") or "duck")
    result = dict(params)
    result["greeting"] = f"{prefix}:{name}"
    result["generated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    return result
