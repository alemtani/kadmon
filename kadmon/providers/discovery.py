"""Find providers that already work on this machine.

Init detects before it asks, so it never prompts for a key the user has already
set somewhere else.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from kadmon.config import (
    KIND_ANTHROPIC,
    KIND_BEDROCK,
    KIND_DEFAULTS,
    KIND_GEMINI,
    KIND_GROK,
    KIND_OPENAI,
    ProviderConfig,
)


@dataclass
class Candidate:
    """A provider init can offer, and why it is or is not available."""

    name: str
    kind: str
    label: str
    available: bool
    detail: str
    model: str = ""
    base_url: str = ""
    auth: str = ""

    def to_config(self) -> ProviderConfig:
        return ProviderConfig(
            name=self.name,
            kind=self.kind,
            model=self.model or KIND_DEFAULTS[self.kind]["model"],
            base_url=self.base_url,
            auth=self.auth,
        )


def _env_candidate(
    name: str, kind: str, label: str, var: str = "", model: str = ""
) -> Candidate:
    var = var or KIND_DEFAULTS[kind]["env"]
    found = bool(os.environ.get(var))
    return Candidate(
        name=name,
        kind=kind,
        label=label,
        available=found,
        detail=f"{var} is set" if found else f"{var} not set",
        model=model,
        auth=f"env:{var}",
    )


def _grok_candidate() -> Candidate:
    """Grok is available when a subscription session exists, key or no key.

    A signed-in user must never be told "XAI_API_KEY not set".
    """
    from kadmon.config import stored_grok_grant

    grant = stored_grok_grant()
    if grant is None:
        return _env_candidate("grok", KIND_GROK, "xAI Grok")

    who = grant.account or "your xAI account"
    return Candidate(
        name="grok",
        kind=KIND_GROK,
        label="xAI Grok",
        available=True,
        detail=f"signed in as {who} — runs on your SuperGrok pool",
        auth="oauth:grok",
    )


def _aws_candidate() -> Candidate:
    aws_dir = Path.home() / ".aws"
    found = (aws_dir / "credentials").exists() or (aws_dir / "config").exists()
    return Candidate(
        name="bedrock",
        kind=KIND_BEDROCK,
        label="AWS Bedrock",
        available=found,
        detail="~/.aws found" if found else "no ~/.aws credentials",
    )


def discover() -> list[Candidate]:
    """List every provider kadmon could configure, available or not.

    Order is usage popularity, then Bedrock.
    """
    return [
        _env_candidate("anthropic", KIND_ANTHROPIC, "Anthropic"),
        _env_candidate("openai", KIND_OPENAI, "OpenAI"),
        _grok_candidate(),
        _env_candidate("gemini", KIND_GEMINI, "Google Gemini"),
        _aws_candidate(),
    ]
