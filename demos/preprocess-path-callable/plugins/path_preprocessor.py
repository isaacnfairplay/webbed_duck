from __future__ import annotations

from datetime import date
from typing import Mapping

from webbed_duck.server.preprocess import PreprocessContext


def path_greeting(
    params: Mapping[str, object],
    *,
    context: PreprocessContext,
    salutation: str = "hello",
) -> Mapping[str, object]:
    """Simple file-based preprocessor that stamps the run date."""

    name = str(params.get("name") or "duck")
    result = dict(params)
    result["greeting"] = f"{salutation} {name}"
    result["run_date"] = date.today().isoformat()
    return result
