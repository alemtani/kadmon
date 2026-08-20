"""xAI Grok provider for kadmon."""

from kadmon.providers.openai_provider import OpenAIProvider

XAI_BASE_URL = "https://api.x.ai/v1"
DEFAULT_GROK_MODEL = "grok-4.6"


class GrokProvider(OpenAIProvider):
    """LLM provider using the xAI Grok API.

    Grok speaks the OpenAI chat-completions protocol, so this class reuses
    OpenAIProvider and pins the xAI base URL.
    """

    def __init__(
        self,
        model: str = DEFAULT_GROK_MODEL,
        api_key: str = "",
        max_tokens: int = 8192,
        base_url: str = "",
    ) -> None:
        super().__init__(
            model=model,
            api_key=api_key,
            max_tokens=max_tokens,
            base_url=base_url or XAI_BASE_URL,
        )
