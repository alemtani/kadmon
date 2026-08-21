"""Build a provider from configuration.

Every provider in kadmon is constructed here. Nothing else should import a
provider class directly — that is how `kadmon init` came to be ignored.
"""

import os

import click

from kadmon.config import (
    KIND_ANTHROPIC,
    KIND_BEDROCK,
    KIND_GEMINI,
    KIND_GROK,
    KIND_OPENAI,
    ProviderConfig,
)


def build_provider(config: ProviderConfig, max_tokens: int = 8192, api_key: str = ""):
    """Create the LLM provider described by `config`.

    Pass `api_key` to force a key for this run. The CLI does that when a user
    answers the sign-in prompt with a key. Nothing here ever prompts: `eval` and
    `bench` build providers with no terminal.
    """
    provider = _construct(config, max_tokens, api_key)
    provider.name = config.name
    return provider


def _construct(config: ProviderConfig, max_tokens: int, forced_key: str = ""):
    if config.kind == KIND_BEDROCK:
        from kadmon.providers.bedrock import BedrockProvider

        return BedrockProvider(
            model=config.model, aws_region=config.aws_region, max_tokens=max_tokens
        )

    if config.kind == KIND_GROK and not forced_key:
        provider = _grok_on_subscription(config, max_tokens)
        if provider is not None:
            return provider

    api_key = forced_key or config.resolve_key()

    if config.kind == KIND_ANTHROPIC:
        from kadmon.providers.anthropic import AnthropicProvider

        return AnthropicProvider(model=config.model, api_key=api_key, max_tokens=max_tokens)

    if config.kind == KIND_GEMINI:
        from kadmon.providers.gemini import GeminiProvider

        return GeminiProvider(model=config.model, api_key=api_key, max_tokens=max_tokens)

    if config.kind == KIND_GROK:
        from kadmon.providers.grok import GrokProvider

        return GrokProvider(
            model=config.model,
            api_key=api_key,
            max_tokens=max_tokens,
            base_url=config.base_url,
        )

    if config.kind == KIND_OPENAI:
        from kadmon.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(
            model=config.model,
            api_key=api_key,
            max_tokens=max_tokens,
            base_url=config.base_url,
        )

    raise ValueError(f"Unsupported provider kind: {config.kind}")


def _grok_on_subscription(config: ProviderConfig, max_tokens: int):
    """Build Grok on a live subscription, or return None when there is none.

    This runs before `resolve_key`, which raises when no key is set. A live
    grant wins on its own — `auth = "oauth:grok"` only records where the
    credential came from, so a config that never gained that line still works.
    """
    from kadmon.auth import xai
    from kadmon.providers.grok import GrokProvider

    grant = xai.live_grant()
    if grant is None:
        return None

    for line in _subscription_notices(config):
        click.echo(line, err=True)

    return GrokProvider(model=config.model, max_tokens=max_tokens, grant=grant)


def _subscription_notices(config: ProviderConfig) -> list[str]:
    """One line each for anything the subscription overrode."""
    from kadmon.providers.grok import PROXY_BASE_URL

    lines = ["Running on your SuperGrok subscription pool."]
    if os.environ.get("XAI_API_KEY"):
        lines.append("XAI_API_KEY is set and ignored — a key bills per token.")
    if config.base_url and config.base_url.rstrip("/") != PROXY_BASE_URL:
        lines.append(f"base_url {config.base_url} overridden with {PROXY_BASE_URL}.")
    return lines
