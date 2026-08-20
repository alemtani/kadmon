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
        _env_candidate("grok", KIND_GROK, "xAI Grok"),
        _env_candidate("gemini", KIND_GEMINI, "Google Gemini"),
        _aws_candidate(),
    ]
