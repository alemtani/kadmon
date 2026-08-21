"""Build a provider from configuration.

Every provider in kadmon is constructed here. Nothing else should import a
provider class directly — that is how `kadmon init` came to be ignored.
"""

import os

import click

from kadmon.auth.store import Grant
from kadmon.auth.vendor import Vendor
from kadmon.config import (
    KIND_ANTHROPIC,
    KIND_BEDROCK,
    KIND_DEFAULTS,
    KIND_GEMINI,
    KIND_GROK,
    KIND_OPENAI,
    ProviderConfig,
)

# Kinds whose LLM class accepts a grant (GrantClient). Hosts stay per provider
# — a Codex grant must not hit the SuperGrok proxy, and vice versa.
_GRANT_KINDS = frozenset({KIND_GROK, KIND_OPENAI})


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

    if not forced_key:
        provider = _on_subscription(config, max_tokens)
        if provider is not None:
            return provider

    api_key = forced_key or config.resolve_key()
    return _build_llm(config, max_tokens, api_key=api_key)


def _on_subscription(config: ProviderConfig, max_tokens: int):
    """Build on a live grant for `config.kind`, or None when there is none.

    Looks up the vendor registry by kind, not a Grok-only helper. A live grant
    wins on its own — `auth = "oauth:<vendor>"` only records where the
    credential came from.
    """
    from kadmon.auth import live

    if config.kind not in _GRANT_KINDS:
        return None
    vendor = _vendor_for(config.kind)
    if vendor is None:
        return None

    grant = live(config.kind)
    if grant is None:
        return None

    provider = _build_llm(config, max_tokens, grant=grant, vendor=vendor)
    for line in _subscription_notices(config, vendor, provider):
        click.echo(line, err=True)
    return provider


def _build_llm(
    config: ProviderConfig,
    max_tokens: int,
    api_key: str = "",
    grant: Grant | None = None,
    vendor: Vendor | None = None,
):
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
            grant=grant,
            vendor=vendor,
        )

    if config.kind == KIND_OPENAI:
        from kadmon.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(
            model=config.model,
            api_key=api_key,
            max_tokens=max_tokens,
            base_url=config.base_url,
            grant=grant,
            vendor=vendor,
        )

    raise ValueError(f"Unsupported provider kind: {config.kind}")


def _vendor_for(kind: str):
    from kadmon.auth import find_vendor

    return find_vendor(kind)


def _subscription_notices(config: ProviderConfig, vendor: Vendor, provider) -> list[str]:
    """One line each for anything the subscription overrode."""
    lines = []
    if vendor.run_notice:
        lines.append(vendor.run_notice)
    env_name = KIND_DEFAULTS.get(config.kind, {}).get("env") or vendor.key_env
    if env_name and os.environ.get(env_name):
        lines.append(f"{env_name} is set and ignored — a key bills per token.")
    used = str(getattr(provider, "base_url", "") or "").rstrip("/")
    configured = (config.base_url or "").rstrip("/")
    if configured and used and configured != used:
        lines.append(f"base_url {config.base_url} overridden with {used}.")
    return lines
