from __future__ import annotations

import sys
from types import ModuleType

import pytest

from webbed_duck.server.email import load_email_sender


def _install_module(name: str, **attrs) -> None:
    module = ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module


def test_load_email_sender_accepts_module_colon(monkeypatch):
    def send_email(*args, **kwargs):  # pragma: no cover - execution not needed
        pass

    module_name = "tests.email_sender_colon"
    _install_module(module_name, send_email=send_email)

    sender = load_email_sender(f"{module_name}:send_email")
    assert sender is send_email

    monkeypatch.delitem(sys.modules, module_name, raising=False)


def test_load_email_sender_accepts_dotted_path(monkeypatch):
    module_name = "tests.email_sender_dotted"

    def send_email(*args, **kwargs):  # pragma: no cover - execution not needed
        pass

    _install_module(module_name, send_email=send_email)

    sender = load_email_sender(f"{module_name}.send_email")
    assert sender is send_email

    monkeypatch.delitem(sys.modules, module_name, raising=False)


def test_load_email_sender_rejects_non_callable(monkeypatch):
    module_name = "tests.email_sender_invalid"
    _install_module(module_name, send_email="not-callable")

    with pytest.raises(TypeError):
        load_email_sender(f"{module_name}:send_email")

    monkeypatch.delitem(sys.modules, module_name, raising=False)


def test_load_email_sender_allows_missing_path():
    assert load_email_sender(None) is None
    assert load_email_sender("") is None


def test_load_email_sender_requires_delimiter():
    with pytest.raises(ValueError, match="module:callable or module.attr"):
        load_email_sender("module")
