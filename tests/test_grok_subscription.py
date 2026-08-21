"""A SuperGrok subscription drives the run. A key is the fallback.

Every test is offline. The token endpoint and the proxy are faked.
"""

import time
import typing

import httpx
import openai
import pytest
from click.testing import CliRunner

from kadmon import cli
from kadmon.auth import xai
from kadmon.config import ConfigError, ProviderConfig, load_settings
from kadmon.providers.factory import build_provider
from kadmon.providers.grok import (
    CLI_HEADERS,
    POOL_SPENT,
    PROXY_BASE_URL,
    SESSION_ENDED,
    XAI_BASE_URL,
    GrokProvider,
    PoolExhausted,
)

TOKEN_PAYLOAD = {"access_token": "fresh-token", "refresh_token": "refresh-2", "expires_in": 3600}


@pytest.fixture
def config_home(tmp_path, monkeypatch):
    """Point the global config and credentials at a temp directory."""
    home = tmp_path / "config"
    home.mkdir()
    monkeypatch.setattr("kadmon.config.GLOBAL_CONFIG_PATH", home / "config.toml")
    monkeypatch.setattr("kadmon.config.CREDENTIALS_PATH", home / "credentials.toml")
    monkeypatch.delenv("KADMON_PROVIDER", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    return home


@pytest.fixture
def signed_in():
    """Store a grant that is live and does not need a refresh."""
    grant = xai.Grant(
        access_token="access-1",
        refresh_token="refresh-1",
        expires_at=int(time.time()) + 3600,
        account="me@example.com",
    )
    xai.save_grant(grant)
    return grant


@pytest.fixture
def signed_in_expired():
    """Store a grant whose access token is due for a refresh."""
    grant = xai.Grant(
        access_token="stale",
        refresh_token="refresh-1",
        expires_at=int(time.time()) - 1,
        account="me@example.com",
    )
    xai.save_grant(grant)
    return grant


def api_error(status: int) -> openai.APIStatusError:
    """The error the OpenAI SDK raises for an HTTP status."""
    request = httpx.Request("POST", f"{PROXY_BASE_URL}/chat/completions")
    response = httpx.Response(status, request=request)
    if status == 401:
        return openai.AuthenticationError("unauthorized", response=response, body=None)
    if status == 429:
        return openai.RateLimitError("slow down", response=response, body=None)
    return openai.APIStatusError(f"status {status}", response=response, body=None)


def fake_create(provider, outcomes: list):
    """Answer each proxy call from a queue. Raise anything that is an exception."""
    calls: list[dict] = []
    queue = list(outcomes)

    def _create(**kwargs):
        calls.append(kwargs)
        result = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(result, Exception):
            raise result
        return result

    provider.client.chat.completions.create = _create
    return calls


def grok_config(**overrides) -> ProviderConfig:
    fields = {"name": "grok", "kind": "grok", "model": "grok-4.6"}
    fields.update(overrides)
    return ProviderConfig(**fields)


# --- 2, 3, 4: a grant is enough on its own ---


def test_run_signed_in_needs_no_key(config_home, signed_in, capsys):
    """U1's Grok half: no XAI_API_KEY, no credentials.toml, the run still works."""
    provider = build_provider(grok_config())

    assert isinstance(provider, GrokProvider)
    assert str(provider.client.base_url).startswith(PROXY_BASE_URL)
    assert provider.client.api_key == "access-1"
    assert not (config_home / "credentials.toml").exists()
    assert "SuperGrok" in capsys.readouterr().err


def test_cold_start_grant_only(config_home, signed_in, tmp_path):
    """No config.toml at all. Discovery and resolve both accept the grant."""
    from kadmon.providers.discovery import discover

    grok = next(c for c in discover() if c.name == "grok")
    assert grok.available
    assert "signed in" in grok.detail

    config = load_settings(tmp_path).resolve()
    assert config.kind == "grok"
    assert config.auth == "oauth:grok"


def test_init_with_live_grant_never_prompts_for_key(config_home, signed_in, monkeypatch):
    """`kadmon init` with a live grant asks nothing about keys."""
    monkeypatch.setattr(cli, "_test_provider", lambda config: (True, "connected"))

    result = CliRunner().invoke(cli.main, ["init"], input="3\n\n")

    assert result.exit_code == 0, result.output
    assert "API key" not in result.output
    assert not (config_home / "credentials.toml").exists()
    assert 'auth = "oauth:grok"' in (config_home / "config.toml").read_text()


# --- 7, 8, 9: a dead session is not a spent pool ---


def dead_refresh(monkeypatch):
    """Make every token request fail, which is what a dead grant looks like."""

    def _post_form(url, fields, timeout=30.0):
        raise xai._OAuthError("invalid_grant", "refresh token revoked")

    monkeypatch.setattr(xai, "_post_form", _post_form)


def test_dead_grant_at_start_offers_key_on_tty(config_home, signed_in_expired, monkeypatch):
    """A terminal may take a key. The key is not stored without a second yes."""
    dead_refresh(monkeypatch)
    monkeypatch.setattr(cli, "_is_tty", lambda: True)

    runner = CliRunner()
    with runner.isolation(input="xai-typed-key\nn\n") as (out, err, _):
        provider = cli._make_provider(None, None, None, str(config_home))
    output = out.getvalue().decode() + err.getvalue().decode()

    assert "session ended" in output
    assert "bills per token" in output, "the trade must be visible"
    assert str(provider.client.base_url).startswith(XAI_BASE_URL)
    assert provider.client.api_key == "xai-typed-key"
    assert not (config_home / "credentials.toml").exists(), "no second yes, no stored key"


def test_dead_grant_no_tty_stops(config_home, signed_in_expired, monkeypatch):
    """`eval` and `bench` have no terminal, so nothing may ask them anything."""
    dead_refresh(monkeypatch)
    monkeypatch.setattr(cli, "_is_tty", lambda: False)

    runner = CliRunner()
    with runner.isolation() as (out, err, _), pytest.raises(SystemExit):
        cli._make_provider(None, None, None, str(config_home))

    assert "sign in again" in out.getvalue().decode() + err.getvalue().decode()


def test_factory_never_prompts_without_a_terminal(config_home, signed_in_expired, monkeypatch):
    """The factory raises. It does not ask, and it does not reach for a key."""
    dead_refresh(monkeypatch)
    monkeypatch.setenv("XAI_API_KEY", "console-key")

    with pytest.raises(xai.AuthError):
        build_provider(grok_config())


def test_dead_grant_midrun_stops(config_home, signed_in, monkeypatch):
    """A rejected token mid-run refreshes once. A second rejection stops the run."""
    monkeypatch.setenv("XAI_API_KEY", "console-key")
    provider = build_provider(grok_config())
    calls = fake_create(provider, [api_error(401), api_error(401)])
    monkeypatch.setattr(xai, "_post_form", lambda url, fields, timeout=30.0: TOKEN_PAYLOAD)

    with pytest.raises(xai.AuthError) as caught:
        provider.complete(messages=[])

    assert str(caught.value) == SESSION_ENDED
    assert len(calls) == 2, "refresh once, retry once, then stop"
    assert provider.client.api_key != "console-key", "never swap in the key"


def test_401_refreshes_once_and_succeeds(config_home, signed_in, monkeypatch):
    """The ordinary case: the token was stale, the retry works, the run continues."""
    provider = build_provider(grok_config())
    fake_create(provider, [api_error(401), _one_response()])
    monkeypatch.setattr(xai, "_post_form", lambda url, fields, timeout=30.0: TOKEN_PAYLOAD)

    response = provider.complete(messages=[])

    assert response.content == "ok"
    assert provider.client.api_key == "fresh-token"


# --- 10, 11: a spent pool never becomes a key ---


def test_pool_exhausted_never_falls_back_to_key(config_home, signed_in, monkeypatch):
    """A 402 stops the run even when a valid XAI_API_KEY is sitting right there."""
    monkeypatch.setenv("XAI_API_KEY", "console-key")
    provider = build_provider(grok_config())
    calls = fake_create(provider, [api_error(402)])

    with pytest.raises(PoolExhausted) as caught:
        provider.complete(messages=[])

    assert str(caught.value) == POOL_SPENT
    assert len(calls) == 1, "a spent pool is not a rate limit — do not retry it"
    assert provider.client.api_key == "access-1"
    assert str(provider.client.base_url).startswith(PROXY_BASE_URL)


def test_pool_exhaustion_stops_the_cli(monkeypatch):
    """The CLI reports it in one line and stops. It never offers a key."""
    monkeypatch.setattr(cli, "_is_tty", lambda: False)
    runner = CliRunner()

    with (
        runner.isolation() as (out, err, _),
        pytest.raises(SystemExit),
        cli._subscription_limits(),
    ):
        raise PoolExhausted(POOL_SPENT)

    output = out.getvalue().decode() + err.getvalue().decode()
    assert len(output.strip().splitlines()) == 1
    assert "key" not in output.lower().replace("pay-per-token api key", "")


def test_pool_exhaustion_and_dead_grant_differ():
    """One means wait. The other means sign in again. They must not read alike."""
    assert POOL_SPENT != SESSION_ENDED
    assert "sign in" not in POOL_SPENT.lower()
    assert "pool" not in SESSION_ENDED.lower()


def test_429_is_still_a_retryable_rate_limit(config_home, signed_in, monkeypatch):
    """An ordinary rate limit keeps its retry. Only 402 stops."""
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    provider = build_provider(grok_config())
    calls = fake_create(provider, [api_error(429), _one_response()])

    assert provider.complete(messages=[]).content == "ok"
    assert len(calls) == 2


# --- 13, 14, 15, 16: precedence and transport ---


def test_subscription_beats_key(config_home, signed_in, monkeypatch, capsys):
    """Both present. The subscription wins, and the ignored key is named."""
    monkeypatch.setenv("XAI_API_KEY", "console-key")

    provider = build_provider(grok_config())
    notices = capsys.readouterr().err

    assert str(provider.client.base_url).startswith(PROXY_BASE_URL)
    assert provider.client.api_key == "access-1"
    assert "XAI_API_KEY" in notices and "ignored" in notices


def test_key_only_uses_console_host(config_home, monkeypatch):
    """Not signed in. A key goes to the console host, which bills per token."""
    monkeypatch.setenv("XAI_API_KEY", "console-key")

    provider = build_provider(grok_config())

    assert str(provider.client.base_url).startswith(XAI_BASE_URL)
    assert provider.client.api_key == "console-key"


def test_grant_overrides_configured_base_url(config_home, signed_in, capsys):
    """A grant sent to api.x.ai would bill the console meter. Pin the proxy."""
    provider = build_provider(grok_config(base_url=XAI_BASE_URL))
    notices = capsys.readouterr().err

    assert str(provider.client.base_url).startswith(PROXY_BASE_URL)
    assert XAI_BASE_URL in notices and "overridden" in notices


def test_no_duplicate_auth_header(config_home, signed_in):
    """The token rides as api_key. Two auth headers would compete."""
    provider = build_provider(grok_config())

    assert provider.client.api_key == "access-1"
    assert not any(h.lower() == "authorization" for h in CLI_HEADERS)
    sent = {k.lower(): v for k, v in provider.client.default_headers.items()}
    assert sent.get("authorization") in (None, "")
    assert sent["x-grok-client-identifier"] == "grok-shell"


def test_oauth_on_a_non_grok_kind_is_a_config_error(config_home, tmp_path):
    """`oauth:` records a Grok sign-in. No other kind has one."""
    (config_home / "config.toml").write_text(
        '[providers.claude]\nkind = "anthropic"\nauth = "oauth:claude"\n'
    )
    with pytest.raises(ConfigError, match="no sign-in"):
        load_settings(tmp_path)


def test_oauth_record_alone_does_not_sign_you_in(config_home, monkeypatch):
    """The record is not the switch. With no grant and no key, say how to fix it."""
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="kadmon login grok"):
        build_provider(grok_config(auth="oauth:grok"))


def test_grant_wins_without_the_oauth_record(config_home, signed_in):
    """A config that never gained `auth = "oauth:grok"` still uses the grant."""
    provider = build_provider(grok_config(auth="env:XAI_API_KEY"))

    assert str(provider.client.base_url).startswith(PROXY_BASE_URL)


# --- 17: the stream path is not a second, unguarded transport ---


def test_stream_path_refreshes_and_stops(config_home, signed_in, monkeypatch):
    """`kadmon chat` streams. Refresh, retry, and the pool stop must reach it."""
    provider = build_provider(grok_config())
    calls = fake_create(provider, [api_error(401), iter([])])
    monkeypatch.setattr(xai, "_post_form", lambda url, fields, timeout=30.0: TOKEN_PAYLOAD)

    chunks = list(provider.stream(messages=[]))

    assert len(calls) == 2, "stream() must go through the same retry as complete()"
    assert provider.client.api_key == "fresh-token"
    assert chunks[-1].event.value == "done"

    fake_create(provider, [api_error(402)])
    with pytest.raises(PoolExhausted):
        list(provider.stream(messages=[]))


def _one_response():
    """The smallest chat-completions body the parser accepts."""

    class _Message:
        content = "ok"
        tool_calls = None

    class _Choice:
        message = _Message()
        finish_reason = "stop"

    class _Response:
        choices: typing.ClassVar = [_Choice()]
        usage = None

    return _Response()
