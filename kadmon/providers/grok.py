"""xAI Grok provider for kadmon.

Grok has two transports. A console API key goes to `api.x.ai/v1` and bills per
token. A subscription grant goes to `cli-chat-proxy.grok.com/v1` and draws from
the SuperGrok pool. A live grant always wins — see `docs/subscription-auth.md`.
"""

from kadmon.auth.store import Grant
from kadmon.auth.vendor import Vendor
from kadmon.providers.openai_provider import OpenAIProvider
from kadmon.providers.subscription import GrantClient

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


class GrokProvider(GrantClient, OpenAIProvider):
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
        grant: Grant | None = None,
        vendor: Vendor | None = None,
    ) -> None:
        self.grant = grant
        self.vendor = vendor
        if grant is not None:
            # A grant sent to api.x.ai bills the console meter. Pin the proxy.
            api_key = grant.access_token
            base_url = PROXY_BASE_URL
            if self.vendor is None:
                from kadmon.auth import find_vendor

                self.vendor = find_vendor("grok")

        super().__init__(
            model=model,
            api_key=api_key,
            max_tokens=max_tokens,
            base_url=base_url or XAI_BASE_URL,
            default_headers=CLI_HEADERS if grant is not None else None,
        )
