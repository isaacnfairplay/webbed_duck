from pathlib import Path

import pytest

from webbed_duck.server.share import ShareError, ShareStore


def test_share_store_single_use(tmp_path: Path) -> None:
    store = ShareStore(tmp_path)
    token = store.create_share(
        route_id="hello",
        params={"name": "world"},
        payload={"rows": [{"greeting": "hi"}], "columns": ["greeting"]},
        ttl_minutes=1,
        bind_user_agent=True,
        bind_ip_prefix=True,
        user_agent="pytest-agent",
        ip_address="10.0.0.5",
        owner_user_id="user-1",
        owner_email_hash="hash",
    )

    record = store.consume_share(token.token, user_agent="pytest-agent", ip_address="10.0.0.5")
    assert record.route_id == "hello"
    assert record.params["name"] == "world"
    assert record.payload["rows"][0]["greeting"] == "hi"
    assert record.uses == 1

    with pytest.raises(ShareError) as excinfo:
        store.consume_share(token.token, user_agent="pytest-agent", ip_address="10.0.0.5")
    assert excinfo.value.code in {"invalid_token", "share_used"}


def test_share_store_binding_enforced(tmp_path: Path) -> None:
    store = ShareStore(tmp_path)
    reusable = store.create_share(
        route_id="hello",
        params={},
        payload={"rows": []},
        ttl_minutes=1,
        bind_user_agent=True,
        bind_ip_prefix=True,
        user_agent=None,
        ip_address=None,
        owner_user_id=None,
        owner_email_hash=None,
        max_uses=2,
    )

    first = store.consume_share(reusable.token, user_agent="Agent/1", ip_address="203.0.113.9")
    assert first.uses == 1
    second = store.consume_share(reusable.token, user_agent="Agent/1", ip_address="203.0.113.9")
    assert second.uses == 2

    another = store.create_share(
        route_id="hello",
        params={},
        payload={"rows": []},
        ttl_minutes=1,
        bind_user_agent=True,
        bind_ip_prefix=True,
        user_agent=None,
        ip_address=None,
        owner_user_id=None,
        owner_email_hash=None,
        max_uses=2,
    )

    store.consume_share(another.token, user_agent="Agent/1", ip_address="203.0.113.9")
    with pytest.raises(ShareError) as mismatch:
        store.consume_share(another.token, user_agent="Agent/2", ip_address="203.0.113.9")
    assert mismatch.value.code == "user_agent_mismatch"


def test_share_store_expiry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = ShareStore(tmp_path)
    token = store.create_share(
        route_id="hello",
        params={},
        payload={"rows": []},
        ttl_minutes=1,
        bind_user_agent=False,
        bind_ip_prefix=False,
        user_agent=None,
        ip_address=None,
        owner_user_id=None,
        owner_email_hash=None,
    )
    from webbed_duck.server import share as share_mod

    base = share_mod.time.time()
    monkeypatch.setattr(share_mod.time, "time", lambda: base + 400)

    with pytest.raises(ShareError) as expired:
        store.consume_share(token.token, user_agent=None, ip_address=None)
    assert expired.value.code == "share_expired"
