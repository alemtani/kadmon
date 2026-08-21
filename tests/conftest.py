"""Shared fixtures. Every test runs offline and touches no real credential."""

import pytest

from kadmon.auth import store


@pytest.fixture(autouse=True)
def isolated_token_store(tmp_path, monkeypatch):
    """Point the token store at a temp path for every test.

    A live grant on the developer's machine must never change what a test does.
    """
    monkeypatch.setattr(store, "TOKENS_PATH", tmp_path / "tokens" / "tokens.toml")
