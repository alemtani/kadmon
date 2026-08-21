"""Shared auth store and vendor dispatch. Every test is offline."""

import tomllib
from collections.abc import Callable

import pytest
from click.testing import CliRunner

from kadmon.auth import Grant, LoginPrompt, Vendor, register, store, unregister
from kadmon.cli import main


@pytest.fixture
def token_store(tmp_path, monkeypatch):
    path = tmp_path / "config" / "tokens.toml"
    monkeypatch.setattr(store, "TOKENS_PATH", path)
    return path


class _StubVendor(Vendor):
    """A second vendor used only to prove dispatch. Not a real provider."""

    name = "stub"
    display_name = "Stub"
    tested = False
    success_hint = "Stub is wired, not verified."

    def login(self, show: Callable[[LoginPrompt], None]) -> Grant:
        show(LoginPrompt(url="https://example.test/device", user_code="STUB-1"))
        return Grant("stub-access", account="stub@example.com", extra={"id_token": "idt"})


def test_save_preserves_other_vendor_extra_keys(token_store):
    store.save(
        "codex",
        Grant("codex-access", extra={"id_token": "idt", "account_id": "acct-1"}),
    )
    store.save("grok", Grant("grok-access", "refresh-1", 1, "me@example.com"))

    stored = tomllib.loads(token_store.read_text())
    assert stored["codex"]["id_token"] == "idt"
    assert stored["codex"]["account_id"] == "acct-1"
    assert stored["grok"]["access_token"] == "grok-access"


def test_load_round_trips_extra_keys(token_store):
    store.save("codex", Grant("access", extra={"id_token": "idt"}))

    grant = store.load("codex")
    assert grant is not None
    assert grant.extra["id_token"] == "idt"


def test_login_dispatches_to_a_registered_vendor(token_store):
    register(_StubVendor())
    try:
        result = CliRunner().invoke(main, ["login", "stub"])
    finally:
        unregister("stub")

    assert result.exit_code == 0, result.output
    assert "experimental" in result.output
    assert "may not be fully tested" in result.output
    assert "STUB-1" in result.output
    assert "stub@example.com" in result.output
    assert store.load("stub") is not None
    assert store.load("stub").extra["id_token"] == "idt"


def test_unknown_vendor_is_refused(token_store):
    result = CliRunner().invoke(main, ["login", "codex"])

    assert result.exit_code != 0
    assert "codex" in result.output
    assert "grok" in result.output
