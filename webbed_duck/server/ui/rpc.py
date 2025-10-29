"""RPC payload helpers."""
from __future__ import annotations

import html
import json
from typing import Mapping


def render_rpc_payload(rpc_payload: Mapping[str, object] | None) -> str:
    if not rpc_payload:
        return ""
    endpoint = rpc_payload.get("endpoint")
    data = {key: value for key, value in rpc_payload.items() if key != "endpoint"}
    if endpoint:
        data["endpoint"] = endpoint
    try:
        payload_json = json.dumps(data, separators=(",", ":"))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        payload_json = "{}"
    link_html = (
        f"<a class='rpc-download' href='{html.escape(str(endpoint))}'>"
        "Download this slice (Arrow)</a>"
        if endpoint
        else ""
    )
    if not link_html and payload_json == "{}":
        return ""
    safe_json = payload_json.replace("</", "<\\/")
    return (
        "<div class='rpc-actions'>"
        + link_html
        + "</div>"
        + "<script type='application/json' id='wd-rpc-config'>"
        + safe_json
        + "</script>"
    )


__all__ = ["render_rpc_payload"]
