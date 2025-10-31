from __future__ import annotations

from webbed_duck.server.cache import InvariantFilterSetting
from webbed_duck.server.ui.invariants import pages_for_other_invariants


def test_pages_for_other_invariants_prefers_numeric_tokens_for_numeric_strings() -> None:
    amount_setting = InvariantFilterSetting(param="amount", column="amount")
    category_setting = InvariantFilterSetting(param="category", column="category")
    invariant_settings = {
        "amount": amount_setting,
        "category": category_setting,
    }
    index = {
        "amount": {
            "str:42": {
                "pages": [1],
                "sample": "42",
            },
            "num:42": {
                "pages": [2, 3],
                "sample": "42",
            },
        },
        "category": {
            "str:books": {
                "pages": [1, 2, 3],
                "sample": "books",
            }
        },
    }

    pages, applied = pages_for_other_invariants(
        "category",
        invariant_settings,
        index,
        {"amount": "42"},
    )

    assert pages == {2, 3}
    assert applied is True
