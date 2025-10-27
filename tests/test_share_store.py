from pathlib import Path

import pytest
from starlette.requests import Request

from webbed_duck.config import load_config
from webbed_duck.server.meta import MetaStore
from webbed_duck.server.share import ShareStore


async def _receive_empty() -> dict[str, object]:
    return {"type": "http.request", "body": b"", "more_body": False}


def _make_request(*, user_agent: str | None, host: str | None) -> Request:
    headers = []
    if user_agent is not None:
        headers.append((b"user-agent", user_agent.encode("utf-8")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
    }
    if host is not None:
        scope["client"] = (host, 0)
    return Request(scope, _receive_empty)


@pytest.fixture()
def share_store(tmp_path: Path) -> ShareStore:
    config = load_config(None)
    config.server.storage_root = tmp_path
    config.email.bind_share_to_user_agent = True
    config.email.bind_share_to_ip_prefix = True
    meta = MetaStore(tmp_path)
    return ShareStore(meta, config)


def test_share_store_enforces_user_agent_and_ip_bindings(share_store: ShareStore) -> None:
    create_request = _make_request(user_agent="Browser/1.0", host="192.168.1.9")
    share = share_store.create(
        "route-1",
        params={"name": "Duck"},
        fmt="json",
        redact_columns=("secret", "note"),
        created_by_hash="creator",
        request=create_request,
    )

    matching_request = _make_request(user_agent="Browser/1.0", host="192.168.1.44")
    resolved = share_store.resolve(share.token, matching_request)
    assert resolved is not None
    assert tuple(resolved.redact_columns) == ("note", "secret")

    mismatched_agent = _make_request(user_agent="Other", host="192.168.1.50")
    assert share_store.resolve(share.token, mismatched_agent) is None

    missing_agent = _make_request(user_agent=None, host="192.168.1.77")
    assert share_store.resolve(share.token, missing_agent) is None

    mismatched_ip = _make_request(user_agent="Browser/1.0", host="10.0.0.1")
    assert share_store.resolve(share.token, mismatched_ip) is None


def test_share_store_handles_ipv6_prefix_binding(share_store: ShareStore) -> None:
    create_request = _make_request(user_agent="Browser/1.0", host="2001:db8:abcd:1::1")
    share = share_store.create(
        "route-2",
        params={},
        fmt="json",
        redact_columns=(),
        created_by_hash=None,
        request=create_request,
    )

    matching = _make_request(user_agent="Browser/1.0", host="2001:db8:abcd:1::5")
    assert share_store.resolve(share.token, matching) is not None

    mismatched = _make_request(user_agent="Browser/1.0", host="2001:db8:abcd:2::1")
    assert share_store.resolve(share.token, mismatched) is None
