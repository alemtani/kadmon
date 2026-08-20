"""Every provider must be built through the factory.

`kadmon init` was ignored for a long time because commands constructed providers
directly from environment variables. These tests keep that from coming back.
"""

import ast
from pathlib import Path

import pytest

PROVIDER_CLASSES = {
    "AnthropicProvider",
    "BedrockProvider",
    "OpenAIProvider",
    "GrokProvider",
    "GeminiProvider",
}

# The factory builds providers; the provider modules define them; discovery and
# tests may name them freely.
ALLOWED = {
    "factory.py",
    "anthropic.py",
    "bedrock.py",
    "openai_provider.py",
    "grok.py",
    "gemini.py",
}

PACKAGE = Path(__file__).resolve().parent.parent / "kadmon"


def _modules():
    return [p for p in PACKAGE.rglob("*.py") if p.name not in ALLOWED]


def _constructs_provider(path: Path) -> list[str]:
    """Find direct calls like AnthropicProvider(...) in a module."""
    tree = ast.parse(path.read_text())
    found = []
    for node in ast.walk(tree):
        is_direct_call = isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        if is_direct_call and node.func.id in PROVIDER_CLASSES:
            found.append(f"{path.relative_to(PACKAGE)}:{node.lineno} {node.func.id}")
    return found


@pytest.mark.parametrize("module", _modules(), ids=lambda p: str(p.name))
def test_module_does_not_build_a_provider_directly(module):
    offenders = _constructs_provider(module)
    assert not offenders, (
        "Build providers through kadmon.providers.factory.build_provider so that "
        f"configuration is honored. Direct construction found: {offenders}"
    )


def test_factory_covers_every_kind(monkeypatch):
    """Each configurable kind maps to a provider the factory can build."""
    from kadmon.config import KINDS, ProviderConfig
    from kadmon.providers.factory import build_provider

    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "XAI_API_KEY"):
        monkeypatch.setenv(var, "test-key")

    for kind in KINDS:
        provider = build_provider(ProviderConfig(name=kind, kind=kind, model="test-model"))
        assert provider.model == "test-model", f"{kind} did not receive its model"
        assert provider.name == kind
