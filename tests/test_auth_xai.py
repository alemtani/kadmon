"""Device-code sign-in for xAI Grok. Every test is offline."""

import base64
import json
import stat
import time
import tomllib

import pytest
from click.testing import CliRunner

from kadmon.auth import xai
from kadmon.cli import main


def id_token(email: str) -> str:
    """A fake id token. Only the claims matter — nothing verifies the signature."""
    claims = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"header.{claims}.signature"


@pytest.fixture
def token_store(tmp_path, monkeypatch):
    """Point the token store at a temp directory and stop the polling sleep."""
    path = tmp_path / "config" / "tokens.toml"
    monkeypatch.setattr(xai, "TOKENS_PATH", path)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    return path


def fake_endpoint(monkeypatch, responses: dict[str, list[dict]]):
    """Answer each URL from a queue of canned payloads. No network."""
    calls: list[tuple[str, dict]] = []

    def _post_form(url, fields, timeout=30.0):
        calls.append((url, fields))
        queue = responses[url]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    monkeypatch.setattr(xai, "_post_form", _post_form)
    return calls


DEVICE_RESPONSE = {
    "device_code": "device-code-1",
    "user_code": "ABCD-1234",
    "verification_uri": "https://accounts.x.ai/oauth2/device",
    "verification_uri_complete": "https://accounts.x.ai/oauth2/device?user_code=ABCD-1234",
    "expires_in": 1800,
    "interval": 5,
}

TOKEN_RESPONSE = {
    "access_token": "access-1",
    "refresh_token": "refresh-1",
    "expires_in": 3600,
    "id_token": id_token("someone@example.com"),
}


# --- 1. login_grok_stores_token ---


def test_login_grok_stores_token(token_store, monkeypatch):
    fake_endpoint(
        monkeypatch,
        {xai.DEVICE_CODE_URL: [DEVICE_RESPONSE], xai.TOKEN_URL: [TOKEN_RESPONSE]},
    )

    result = CliRunner().invoke(main, ["login", "grok"])

    assert result.exit_code == 0, result.output
    assert "ABCD-1234" in result.output
    assert "https://accounts.x.ai/oauth2/device?user_code=ABCD-1234" in result.output
    assert "someone@example.com" in result.output

    assert token_store.exists()
    assert stat.S_IMODE(token_store.stat().st_mode) == 0o600

    stored = tomllib.loads(token_store.read_text())
    assert set(stored) == {"grok"}
    assert set(stored["grok"]) == {"access_token", "refresh_token", "expires_at", "account"}
    assert stored["grok"]["access_token"] == "access-1"
    assert stored["grok"]["refresh_token"] == "refresh-1"
    assert stored["grok"]["account"] == "someone@example.com"
    assert stored["grok"]["expires_at"] > time.time()


def test_login_grok_polls_until_the_user_approves(token_store, monkeypatch):
    seen = {"polls": 0}

    def _post_form(url, fields, timeout=30.0):
        if url == xai.DEVICE_CODE_URL:
            return DEVICE_RESPONSE
        seen["polls"] += 1
        if seen["polls"] < 3:
            raise xai._OAuthError("authorization_pending")
        return TOKEN_RESPONSE

    monkeypatch.setattr(xai, "_post_form", _post_form)

    result = CliRunner().invoke(main, ["login", "grok"])

    assert result.exit_code == 0, result.output
    assert seen["polls"] == 3
    assert xai.load_grant().access_token == "access-1"


def test_login_grok_reports_a_denied_request(token_store, monkeypatch):
    def _post_form(url, fields, timeout=30.0):
        if url == xai.DEVICE_CODE_URL:
            return DEVICE_RESPONSE
        raise xai._OAuthError("access_denied")

    monkeypatch.setattr(xai, "_post_form", _post_form)

    result = CliRunner().invoke(main, ["login", "grok"])

    assert result.exit_code == 1
    assert "denied" in result.output
    assert not token_store.exists()


# --- 5. logout_grok_removes_token ---


def test_logout_grok_removes_token(token_store):
    xai.save_grant(xai.Grant("access-1", "refresh-1", int(time.time()) + 3600, "me@example.com"))

    result = CliRunner().invoke(main, ["logout", "grok"])

    assert result.exit_code == 0, result.output
    assert xai.load_grant() is None
    assert "grok" not in tomllib.loads(token_store.read_text())


def test_logout_grok_keeps_other_vendors(token_store):
    xai.save_grant(xai.Grant("access-1", "refresh-1", 0, ""))
    token_store.write_text(
        token_store.read_text() + '\n[kimi]\naccess_token = "other"\nexpires_at = 0\n'
    )

    CliRunner().invoke(main, ["logout", "grok"])

    assert "kimi" in tomllib.loads(token_store.read_text())


def test_logout_grok_when_signed_out_says_so(token_store):
    result = CliRunner().invoke(main, ["logout", "grok"])

    assert result.exit_code == 0
    assert "Not signed in" in result.output


# --- 6. expired_token_refreshes_silently ---


def test_expired_token_refreshes_silently(token_store, monkeypatch, capsys):
    xai.save_grant(
        xai.Grant("stale", "refresh-1", int(time.time()) + 30, "me@example.com"),
    )
    fake_endpoint(
        monkeypatch,
        {xai.TOKEN_URL: [{"access_token": "access-2", "expires_in": 3600}]},
    )

    grant = xai.live_grant()

    assert grant.access_token == "access-2"
    assert capsys.readouterr().out == ""
    # The refresh response carried no refresh token, so the old one survives.
    assert xai.load_grant().refresh_token == "refresh-1"
    assert xai.load_grant().account == "me@example.com"


def test_live_grant_leaves_a_fresh_token_alone(token_store, monkeypatch):
    xai.save_grant(xai.Grant("access-1", "refresh-1", int(time.time()) + 3600, ""))
    calls = fake_endpoint(monkeypatch, {xai.TOKEN_URL: [TOKEN_RESPONSE]})

    assert xai.live_grant().access_token == "access-1"
    assert calls == []


def test_refresh_failure_clears_the_grant(token_store, monkeypatch):
    xai.save_grant(xai.Grant("stale", "refresh-1", int(time.time()) + 30, ""))

    def _post_form(url, fields, timeout=30.0):
        raise xai._OAuthError("invalid_grant")

    monkeypatch.setattr(xai, "_post_form", _post_form)

    with pytest.raises(xai.AuthError, match="sign in again"):
        xai.live_grant()

    assert xai.load_grant() is None


def test_live_grant_survives_a_network_failure(token_store, monkeypatch):
    """A blip is not a dead grant. The stored token must stay."""
    xai.save_grant(xai.Grant("stale", "refresh-1", int(time.time()) + 30, ""))

    def _post_form(url, fields, timeout=30.0):
        raise xai.AuthError("Cannot reach auth.x.ai.")

    monkeypatch.setattr(xai, "_post_form", _post_form)

    with pytest.raises(xai.AuthError):
        xai.live_grant()

    assert xai.load_grant() is not None


# --- 12. login_when_already_signed_in_says_so ---


def test_login_when_already_signed_in_says_so(token_store, monkeypatch):
    xai.save_grant(xai.Grant("access-1", "refresh-1", int(time.time()) + 3600, "me@example.com"))
    calls = fake_endpoint(
        monkeypatch,
        {xai.DEVICE_CODE_URL: [DEVICE_RESPONSE], xai.TOKEN_URL: [TOKEN_RESPONSE]},
    )

    signed_in = CliRunner().invoke(main, ["login", "grok"])

    assert signed_in.exit_code == 0, signed_in.output
    assert calls == [], "an existing grant must not start a new device-code flow"
    assert "Already signed in" in signed_in.output
    assert "me@example.com" in signed_in.output

    # The signed-out flow must not render the same way.
    xai.clear_grant()
    signed_out = CliRunner().invoke(main, ["login", "grok"])

    assert signed_out.output != signed_in.output
    assert "Already signed in" not in signed_out.output
    assert "Open this URL to sign in" in signed_out.output


# --- the store itself ---


def test_write_replaces_the_store_atomically(token_store):
    xai.save_grant(xai.Grant("access-1", "refresh-1", 1, ""))
    token_store.chmod(0o644)

    xai.save_grant(xai.Grant("access-2", "refresh-2", 2, ""))

    assert stat.S_IMODE(token_store.stat().st_mode) == 0o600
    assert list(token_store.parent.glob("*.tmp")) == []
    assert xai.load_grant().access_token == "access-2"


def test_no_grant_when_the_store_is_absent(token_store):
    assert xai.load_grant() is None
