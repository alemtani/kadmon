"""xAI Grok provider for kadmon.

Grok has two transports. A console API key goes to `api.x.ai/v1` and bills per
token. A subscription grant goes to `cli-chat-proxy.grok.com/v1` and draws from
the SuperGrok pool. A live grant always wins — see `docs/subscription-auth.md`.
"""

import openai

from kadmon.providers.openai_provider import OpenAIProvider

XAI_BASE_URL = "https://api.x.ai/v1"
PROXY_BASE_URL = "https://cli-chat-proxy.grok.com/v1"
DEFAULT_GROK_MODEL = "grok-4.6"

# What the Grok CLI sends to identify itself. Captured from its own traffic.
# Identity only — never `Authorization`. The access token rides as `api_key`,
# and the SDK turns that into the one auth header the proxy reads.
CLI_HEADERS = {
    "x-grok-client-identifier": "grok-shell",
    "x-grok-client-version": "1.0.5",
    "x-grok-client-mode": "headless",
    "x-xai-token-auth": "xai-grok-cli",
    "user-agent": "grok-shell/1.0.5 (macos; aarch64)",
}

POOL_SPENT = (
    "Your SuperGrok pool is spent. Wait for it to reset, then run this again. "
    "Kadmon will not move the run onto a pay-per-token API key."
)
SESSION_ENDED = "Your xAI Grok session ended. Run 'kadmon login grok' to sign in again."


class PoolExhausted(Exception):
    """The subscription pool, credit, or spending cap is spent.

    This is not a dead session. It means wait, not sign in again. Never fall
    back to an API key on it.
    """


class GrokProvider(OpenAIProvider):
    """LLM provider using the xAI Grok API.

    Grok speaks the OpenAI chat-completions protocol, so this class reuses
    OpenAIProvider. Pass `grant` to run on a subscription instead of a key.
    """

    def __init__(
        self,
        model: str = DEFAULT_GROK_MODEL,
        api_key: str = "",
        max_tokens: int = 8192,
        base_url: str = "",
        grant=None,
    ) -> None:
        self.grant = grant
        if grant is not None:
            # A grant sent to api.x.ai bills the console meter. Pin the proxy.
            api_key = grant.access_token
            base_url = PROXY_BASE_URL

        super().__init__(
            model=model,
            api_key=api_key,
            max_tokens=max_tokens,
            base_url=base_url or XAI_BASE_URL,
            default_headers=CLI_HEADERS if grant is not None else None,
        )

    def _call_with_retry(self, kwargs: dict):
        """Send the call, refreshing a rejected token once.

        `complete()` and `stream()` both come through here, so both get the
        refresh, the single retry, and the pool-exhaustion stop.
        """
        try:
            return self._guarded(kwargs)
        except openai.AuthenticationError:
            if self.grant is None:
                raise
            self._refresh()
            try:
                return self._guarded(kwargs)
            except openai.AuthenticationError as exc:
                # A fresh token was rejected too. Stop; do not loop.
                raise _auth_error(SESSION_ENDED) from exc

    def _guarded(self, kwargs: dict):
        """Run the inherited retry, but never retry a spent pool."""
        try:
            return super()._call_with_retry(kwargs)
        except openai.APIStatusError as exc:
            if exc.status_code == 402:
                raise PoolExhausted(POOL_SPENT) from exc
            raise

    def _refresh(self) -> None:
        """Trade the refresh token for a new access token, and use it."""
        from kadmon.auth import xai

        self.grant = xai.refresh_grant(self.grant)
        self.client.api_key = self.grant.access_token


def _auth_error(message: str) -> Exception:
    from kadmon.auth import xai

    return xai.AuthError(message)
