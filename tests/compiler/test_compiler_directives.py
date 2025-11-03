"""Unit tests for compiler directive helpers."""

from __future__ import annotations

import json
import string
from typing import Any

import pytest

try:  # pragma: no cover - optional dependency in CI environments
    from hypothesis import given
    from hypothesis import strategies as st
except ModuleNotFoundError:  # pragma: no cover - executed when hypothesis missing
    pytest.skip("hypothesis not installed", allow_module_level=True)

from webbed_duck.core.compiler import (
    RouteDirective,
    _collect_directive_payloads,
    _merge_param_payload,
    _normalize_string_list,
)


@pytest.mark.parametrize(
    "directives, expected",
    [
        (
            [RouteDirective(name="meta", args={}, value="{\"alpha\": 1}")],
            [{"alpha": 1}],
        ),
        (
            [
                RouteDirective(name="meta", args={"foo": "bar"}, value=None),
                RouteDirective(name="meta", args={}, value="payload"),
            ],
            [{"foo": "bar"}, "payload"],
        ),
        (
            [
                RouteDirective(name="meta", args={}, value=None),
                RouteDirective(name="params", args={}, value="{\"ignored\": true}"),
            ],
            [],
        ),
    ],
)
def test_collect_directive_payloads_filters_and_parses(directives, expected):
    """Only matching directives contribute payloads."""

    payloads = _collect_directive_payloads(directives, "meta")
    assert payloads == expected


def _expected_payload(directive: RouteDirective) -> Any | None:
    if directive.value:
        raw = directive.value.strip()
        if raw.startswith("{") or raw.startswith("["):
            return json.loads(raw)
        if directive.args:
            return {str(k): v for k, v in directive.args.items()}
        return raw
    if directive.args:
        return {str(k): v for k, v in directive.args.items()}
    return None


@st.composite
def directive_strategy(draw) -> RouteDirective:
    target_name = "meta"
    name = target_name if draw(st.booleans()) else draw(
        st.sampled_from(["params", "cache", "note", "assets"])
    )
    payload_kind = draw(st.sampled_from(["json", "text", "args", "none"]))
    if payload_kind == "json":
        data = draw(
            st.dictionaries(
                keys=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=4),
                values=st.integers(-3, 3),
                max_size=3,
            )
        )
        return RouteDirective(name=name, args={}, value=json.dumps(data))
    if payload_kind == "text":
        text = draw(
            st.text(
                alphabet=string.ascii_letters,
                min_size=1,
                max_size=6,
            ).filter(lambda s: not s.startswith(("{", "[")))
        )
        return RouteDirective(name=name, args={}, value=text)
    if payload_kind == "args":
        args = draw(
            st.dictionaries(
                keys=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=4),
                values=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=4),
                min_size=1,
                max_size=3,
            )
        )
        return RouteDirective(name=name, args=args, value=None)
    return RouteDirective(name=name, args={}, value=None)


@given(st.lists(directive_strategy(), max_size=6))
def test_collect_directive_payloads_property(directives):
    expected: list[Any] = []
    for directive in directives:
        if directive.name != "meta":
            continue
        payload = _expected_payload(directive)
        if payload is not None:
            expected.append(payload)
    assert _collect_directive_payloads(directives, "meta") == expected


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"id": {"duckdb_type": "INTEGER"}}, {"id": {"duckdb_type": "INTEGER"}}),
        (
            {"id": "INTEGER"},
            {"id": {"duckdb_type": "INTEGER"}},
        ),
        (
            {"active": True},
            {"active": {"default": True}},
        ),
        (
            [
                {"id": "INTEGER"},
                {"active": {"default": False}},
            ],
            {
                "id": {"duckdb_type": "INTEGER"},
                "active": {"default": False},
            },
        ),
    ],
)
def test_merge_param_payload(payload, expected):
    target: dict[str, dict[str, object]] = {}
    _merge_param_payload(target, payload)
    assert target == expected


@st.composite
def param_payload_strategy(draw) -> Any:
    scalar_value = draw(st.one_of(st.text(min_size=1, max_size=5), st.integers(-5, 5)))
    if draw(st.booleans()):
        return {"p": scalar_value}
    mapping = draw(
        st.dictionaries(
            keys=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=4),
            values=st.one_of(
                st.integers(-5, 5),
                st.text(min_size=1, max_size=5),
                st.booleans(),
                st.dictionaries(
                    keys=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=3),
                    values=st.one_of(
                        st.integers(-3, 3), st.text(min_size=1, max_size=5), st.booleans()
                    ),
                    max_size=2,
                ),
            ),
            max_size=3,
        )
    )
    if draw(st.booleans()):
        return mapping
    return list(mapping.items())


@given(st.lists(param_payload_strategy(), max_size=4))
def test_merge_param_payload_sequence_equivalence(payloads):
    direct: dict[str, dict[str, object]] = {}
    _merge_param_payload(direct, payloads)
    iterative: dict[str, dict[str, object]] = {}
    for payload in payloads:
        _merge_param_payload(iterative, payload)
    assert direct == iterative


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, []),
        ("CSV JSON", ["csv", "json"]),
        ("csv, json , arrow", ["csv", "json", "arrow"]),
        (["CSV", "JSON"], ["csv", "json"]),
        (("CSV", "CSV", "ARROW"), ["csv", "csv", "arrow"]),
    ],
)
def test_normalize_string_list(value, expected):
    assert _normalize_string_list(value) == expected


@given(
    st.lists(
        st.one_of(
            st.text(min_size=0, max_size=4),
            st.integers(-5, 5),
            st.none(),
        ),
        max_size=5,
    )
)
def test_normalize_string_list_property(values):
    expected = [str(item).lower() for item in values if item is not None]
    assert _normalize_string_list(values) == expected
