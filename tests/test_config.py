"""Config loading, multi-provider resolution, and the provider factory."""

import pytest

from kadmon.config import (
    DEFAULT_MODE,
    ConfigError,
    ProviderConfig,
    Settings,
    load_settings,
    write_config,
)


@pytest.fixture
def config_home(tmp_path, monkeypatch):
    """Point the global config and credentials at a temp directory."""
    home = tmp_path / "config"
    home.mkdir()
    monkeypatch.setattr("kadmon.config.GLOBAL_CONFIG_PATH", home / "config.toml")
    monkeypatch.setattr("kadmon.config.CREDENTIALS_PATH", home / "credentials.toml")
    monkeypatch.delenv("KADMON_PROVIDER", raising=False)
    return home


def write_global(config_home, text: str) -> None:
    (config_home / "config.toml").write_text(text)


# --- several providers at once ---


def test_loads_several_providers(config_home, tmp_path):
    write_global(config_home, """
default = "anthropic"

[providers.anthropic]
kind = "anthropic"
model = "claude-sonnet-4-6"

[providers.grok]
kind = "grok"
model = "grok-4.6"
""")
    settings = load_settings(tmp_path)

    assert set(settings.providers) == {"anthropic", "grok"}
    assert settings.resolve().name == "anthropic"
    assert settings.resolve("grok").kind == "grok"
    assert settings.resolve("grok").model == "grok-4.6"


def test_unknown_provider_names_the_configured_ones(config_home, tmp_path):
    write_global(config_home, '[providers.anthropic]\nkind = "anthropic"\n')
    with pytest.raises(ConfigError, match="anthropic"):
        load_settings(tmp_path).resolve("nope")


def test_single_provider_needs_no_default(config_home, tmp_path):
    write_global(config_home, '[providers.grok]\nkind = "grok"\n')
    assert load_settings(tmp_path).resolve().name == "grok"


def test_kind_defaults_to_provider_name(config_home, tmp_path):
    write_global(config_home, '[providers.grok]\nmodel = "grok-4.6"\n')
    assert load_settings(tmp_path).resolve().kind == "grok"


def test_several_providers_without_default_is_an_error(config_home, tmp_path):
    write_global(config_home, '[providers.a]\nkind = "anthropic"\n\n[providers.b]\nkind = "gemini"\n')
    with pytest.raises(ConfigError, match="no default"):
        load_settings(tmp_path).resolve()


def test_no_config_tells_you_to_run_init(config_home, tmp_path):
    with pytest.raises(ConfigError, match="kadmon init"):
        load_settings(tmp_path).resolve()


# --- precedence ---


def test_project_overlays_global(config_home, tmp_path):
    write_global(config_home, '[providers.anthropic]\nkind = "anthropic"\nmodel = "global-model"\nauth = "env:A_KEY"\n')
    project = tmp_path / ".kadmon"
    project.mkdir()
    (project / "config.toml").write_text('[providers.anthropic]\nmodel = "project-model"\n')

    config = load_settings(tmp_path).resolve("anthropic")
    assert config.model == "project-model"
    assert config.auth == "env:A_KEY", "unspecified keys fall through to global"


def test_env_var_overrides_configured_default(config_home, tmp_path, monkeypatch):
    write_global(config_home, 'default = "a"\n\n[providers.a]\nkind = "anthropic"\n\n[providers.b]\nkind = "gemini"\n')
    monkeypatch.setenv("KADMON_PROVIDER", "b")
    assert load_settings(tmp_path).resolve().name == "b"


# --- backwards compatibility ---


def test_old_single_provider_config_still_loads(config_home, tmp_path):
    write_global(config_home, """
[provider]
name = "anthropic"
model = "claude-3-opus"

[pricing]
input = 3.0
output = 15.0
""")
    settings = load_settings(tmp_path)

    assert settings.resolve().model == "claude-3-opus"
    assert settings.pricing == {"input": 3.0, "output": 15.0}, "/cost must not regress"


def test_legacy_inline_key_moves_to_credentials(config_home, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    write_global(config_home, """
[provider]
name = "anthropic"
model = "claude-3-opus"
api_key = "sk-legacy"
""")
    assert load_settings(tmp_path).resolve().resolve_key() == "sk-legacy"


def test_inline_api_key_is_rejected_with_instructions(config_home, tmp_path):
    write_global(config_home, '[providers.anthropic]\nkind = "anthropic"\napi_key = "sk-leaked"\n')
    with pytest.raises(ConfigError, match="auth"):
        load_settings(tmp_path)


def test_unknown_kind_lists_valid_kinds(config_home, tmp_path):
    write_global(config_home, '[providers.weird]\nkind = "telepathy"\n')
    with pytest.raises(ConfigError, match="anthropic"):
        load_settings(tmp_path)


# --- secrets ---


def test_missing_key_is_a_clear_error(monkeypatch, config_home):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config = ProviderConfig(name="anthropic", kind="anthropic", model="m")
    with pytest.raises(ConfigError, match="No API key"):
        config.resolve_key()


def test_key_comes_from_the_named_env_var(monkeypatch, config_home):
    monkeypatch.setenv("XAI_API_KEY", "xai-secret")
    config = ProviderConfig(name="grok", kind="grok", model="grok-4.6")
    assert config.resolve_key() == "xai-secret"


def test_local_endpoint_needs_no_key(monkeypatch, config_home):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = ProviderConfig(
        name="local", kind="openai", model="qwen", base_url="http://127.0.0.1:8080/v1"
    )
    assert config.resolve_key() == "not-needed"


def test_a_broken_entry_does_not_block_a_working_one(config_home, tmp_path, monkeypatch):
    """Secrets resolve on use, not on load."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-secret")
    write_global(config_home, """
default = "grok"

[providers.anthropic]
kind = "anthropic"

[providers.grok]
kind = "grok"
""")
    assert load_settings(tmp_path).resolve().resolve_key() == "xai-secret"


# --- writing ---


def test_written_config_round_trips(config_home, tmp_path):
    providers = [
        ProviderConfig(name="anthropic", kind="anthropic", model="claude-sonnet-4-6"),
        ProviderConfig(
            name="grok",
            kind="grok",
            model="grok-4.6",
        ),
    ]
    path = config_home / "config.toml"
    write_config(providers, "anthropic", path)

    settings = load_settings(tmp_path)
    assert set(settings.providers) == {"anthropic", "grok"}
    assert settings.default == "anthropic"
    assert settings.providers["grok"].kind == "grok"
    assert settings.mode == DEFAULT_MODE
    assert "api_key" not in path.read_text(), "secrets never land in config.toml"


def test_write_config_keeps_existing_pricing(config_home, tmp_path):
    write_global(
        config_home,
        '[providers.anthropic]\nkind = "anthropic"\n\n[pricing]\ninput = 3.0\noutput = 15.0\n',
    )
    write_config(
        [ProviderConfig(name="anthropic", kind="anthropic", model="m")],
        "anthropic",
        config_home / "config.toml",
    )
    assert load_settings(tmp_path).pricing == {"input": 3.0, "output": 15.0}


# --- factory ---


def test_grok_kind_builds_grok_provider(monkeypatch):
    from kadmon.providers.factory import build_provider
    from kadmon.providers.grok import GrokProvider

    monkeypatch.setenv("XAI_API_KEY", "xai-secret")
    provider = build_provider(ProviderConfig(name="grok", kind="grok", model="grok-4.6"))
    assert isinstance(provider, GrokProvider)
    assert provider.model == "grok-4.6"
    assert provider.name == "grok"
    assert "api.x.ai" in str(provider.client.base_url)


def test_discover_offers_grok_not_ollama(monkeypatch):
    from kadmon.providers.discovery import discover

    monkeypatch.setenv("XAI_API_KEY", "xai-secret")
    candidates = discover()
    names = [c.name for c in candidates]
    assert "grok" in names
    assert "ollama" not in names
    grok = next(c for c in candidates if c.name == "grok")
    assert grok.kind == "grok"
    assert grok.available


def test_settings_resolve_prefers_explicit_name():
    settings = Settings(
        providers={
            "a": ProviderConfig(name="a", kind="anthropic"),
            "b": ProviderConfig(name="b", kind="gemini"),
        },
        default="a",
    )
    assert settings.resolve("b").name == "b"
