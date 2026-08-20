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
    KIND_OPENAI,
    OLLAMA_BASE_URL,
    XAI_BASE_URL,
    ProviderConfig,
)

OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"


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
    name: str, kind: str, label: str, base_url: str = "", var: str = "", model: str = ""
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
        base_url=base_url,
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


def _ollama_candidate() -> Candidate:
    """Ask Ollama for its model list. That also tells us what is actually pulled."""
    models: list[str] = []
    try:
        import json
        import urllib.request

        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=1.0) as response:
            payload = json.loads(response.read())
        models = [m["name"] for m in payload.get("models", []) if m.get("name")]
        running = True
    except Exception:  # noqa: BLE001 - any failure means Ollama is unusable here
        running = False

    return Candidate(
        name="ollama",
        kind=KIND_OPENAI,
        label="Ollama (local)",
        available=running and bool(models),
        detail=f"{len(models)} model(s) available" if models else "not running",
        model=models[0] if models else "",
        base_url=OLLAMA_BASE_URL,
        auth="",
    )


def discover() -> list[Candidate]:
    """List every provider kadmon could configure, available or not."""
    return [
        _env_candidate("anthropic", KIND_ANTHROPIC, "Anthropic"),
        _env_candidate("grok", KIND_OPENAI, "xAI Grok", XAI_BASE_URL, "XAI_API_KEY", "grok-4"),
        _env_candidate("openai", KIND_OPENAI, "OpenAI"),
        _env_candidate("gemini", KIND_GEMINI, "Google Gemini"),
        _aws_candidate(),
        _ollama_candidate(),
    ]
