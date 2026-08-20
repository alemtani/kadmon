"""Build a provider from configuration.

Every provider in kadmon is constructed here. Nothing else should import a
provider class directly — that is how `kadmon init` came to be ignored.
"""

from kadmon.config import (
    KIND_ANTHROPIC,
    KIND_BEDROCK,
    KIND_GEMINI,
    KIND_OPENAI,
    ProviderConfig,
)


def build_provider(config: ProviderConfig, max_tokens: int = 8192):
    """Create the LLM provider described by `config`."""
    if config.kind == KIND_BEDROCK:
        from kadmon.providers.bedrock import BedrockProvider

        return BedrockProvider(
            model=config.model, aws_region=config.aws_region, max_tokens=max_tokens
        )

    api_key = config.resolve_key()

    if config.kind == KIND_ANTHROPIC:
        from kadmon.providers.anthropic import AnthropicProvider

        return AnthropicProvider(model=config.model, api_key=api_key, max_tokens=max_tokens)

    if config.kind == KIND_GEMINI:
        from kadmon.providers.gemini import GeminiProvider

        return GeminiProvider(model=config.model, api_key=api_key, max_tokens=max_tokens)

    if config.kind == KIND_OPENAI:
        from kadmon.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(
            model=config.model,
            api_key=api_key,
            max_tokens=max_tokens,
            base_url=config.base_url,
        )

    raise ValueError(f"Unsupported provider kind: {config.kind}")
