import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

# Single source of truth for defaults — update here when new models ship
DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-6"
DEFAULT_PROVIDER = "bedrock"
DEFAULT_REGION = "us-east-1"

# Agent modes (controls tool call approval, NOT ambiguity questions)
MODE_YOLO = "yolo"  # No approval needed for any tool call
MODE_CAUTIOUS = "cautious"  # Approve destructive operations (default)
MODE_PARANOID = "paranoid"  # Approve all non-read operations
DEFAULT_MODE = MODE_YOLO  # Default to yolo (agent asks about ambiguity separately)

# Provider kinds kadmon can build. Anything reachable over an OpenAI-compatible
# endpoint (xAI, Ollama, OpenRouter) uses "openai" with a base_url.
KIND_ANTHROPIC = "anthropic"
KIND_OPENAI = "openai"
KIND_GEMINI = "gemini"
KIND_BEDROCK = "bedrock"
KINDS = (KIND_ANTHROPIC, KIND_OPENAI, KIND_GEMINI, KIND_BEDROCK)

# Per-kind defaults used by init and by entries that omit a field.
KIND_DEFAULTS: dict[str, dict[str, str]] = {
    KIND_ANTHROPIC: {"model": "claude-sonnet-4-6", "env": "ANTHROPIC_API_KEY"},
    KIND_OPENAI: {"model": "gpt-4o", "env": "OPENAI_API_KEY"},
    KIND_GEMINI: {"model": "gemini-2.5-flash", "env": "GOOGLE_API_KEY"},
    KIND_BEDROCK: {"model": DEFAULT_MODEL, "env": ""},
}

# Known OpenAI-compatible endpoints init can offer.
XAI_BASE_URL = "https://api.x.ai/v1"
OLLAMA_BASE_URL = "http://localhost:11434/v1"

GLOBAL_CONFIG_DIR = Path.home() / ".config" / "kadmon"
GLOBAL_CONFIG_PATH = GLOBAL_CONFIG_DIR / "config.toml"
CREDENTIALS_PATH = GLOBAL_CONFIG_DIR / "credentials.toml"
PROJECT_CONFIG_RELPATH = Path(".kadmon") / "config.toml"


class ConfigError(Exception):
    """Raised when config is present but unusable. The message tells the user what to do."""


class ProviderConfig(BaseModel):
    """One configured provider. The name is the key it was stored under."""

    name: str
    kind: str
    model: str = ""
    base_url: str = ""
    auth: str = ""
    aws_region: str = DEFAULT_REGION
    aws_profile: str = ""

    def resolve_key(self) -> str:
        """Read the API key this entry points at. Empty is valid for local endpoints.

        Secrets are resolved here, not at load time, so a broken entry you never
        use cannot block a command that does not need it.
        """
        if self.kind == KIND_BEDROCK:
            return ""

        spec = self.auth or f"env:{KIND_DEFAULTS[self.kind]['env']}"
        source, _, ref = spec.partition(":")

        if source == "env":
            key = os.environ.get(ref, "")
        elif source == "credentials":
            key = _read_credential(ref)
        else:
            raise ConfigError(
                f"Provider '{self.name}' has auth = \"{spec}\". "
                'Use "env:VAR_NAME" or "credentials:name".'
            )

        if not key and not self.is_local:
            raise ConfigError(
                f"No API key for provider '{self.name}' ({spec}). "
                f"Set it, or run 'kadmon init' to reconfigure."
            )
        return key or "not-needed"

    @property
    def is_local(self) -> bool:
        """True when base_url points at this machine, where no key is needed."""
        return any(h in self.base_url for h in ("localhost", "127.0.0.1", "[::1]"))


class Settings(BaseModel):
    """Merged configuration. `providers` may hold several entries at once."""

    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    default: str = ""
    max_tokens: int = 200000
    max_iterations: int = 50
    mode: str = DEFAULT_MODE
    pricing: dict[str, float] = Field(default_factory=dict)

    def resolve(self, name: str = "") -> ProviderConfig:
        """Pick a provider by name, falling back to the configured default."""
        wanted = name or os.environ.get("KADMON_PROVIDER", "") or self.default

        if not self.providers:
            raise ConfigError("No providers configured. Run 'kadmon init' to set one up.")

        if not wanted:
            # A single configured provider needs no default declared.
            if len(self.providers) == 1:
                return next(iter(self.providers.values()))
            raise ConfigError(
                f"Several providers configured ({', '.join(sorted(self.providers))}) "
                "but no default. Set `default = \"<name>\"` or pass --provider."
            )

        if wanted not in self.providers:
            known = ", ".join(sorted(self.providers)) or "none"
            raise ConfigError(f"Unknown provider '{wanted}'. Configured: {known}.")

        return self.providers[wanted]


def _read_credential(name: str) -> str:
    if not CREDENTIALS_PATH.exists():
        return ""
    try:
        data = tomllib.loads(CREDENTIALS_PATH.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Cannot read {CREDENTIALS_PATH}: {exc}") from exc
    entry = data.get(name)
    return entry.get("api_key", "") if isinstance(entry, dict) else ""


def _read_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc


def _translate_legacy(raw: dict) -> dict:
    """Convert a pre-multi-provider `[provider]` table into `[providers.*]`.

    Old files carry an inline api_key. We keep it working rather than failing the
    load, but init rewrites it into the credentials file.
    """
    legacy = raw.get("provider")
    if not isinstance(legacy, dict):
        return raw

    kind = legacy.get("name", DEFAULT_PROVIDER)
    entry = {"kind": kind, "model": legacy.get("model", "")}
    for field in ("aws_region", "aws_profile", "base_url"):
        if legacy.get(field):
            entry[field] = legacy[field]

    merged = {k: v for k, v in raw.items() if k != "provider"}
    merged.setdefault("providers", {})
    merged["providers"] = {kind: entry, **merged["providers"]}
    merged.setdefault("default", kind)
    return merged


def _merge(base: dict, overlay: dict) -> dict:
    """Merge an overlay into base, one level deep inside each named table."""
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _build_providers(raw: dict) -> dict[str, ProviderConfig]:
    providers: dict[str, ProviderConfig] = {}
    for name, entry in (raw.get("providers") or {}).items():
        if not isinstance(entry, dict):
            raise ConfigError(f"Provider '{name}' must be a table.")

        kind = entry.get("kind", name)
        if kind not in KINDS:
            raise ConfigError(
                f"Provider '{name}' has unknown kind '{kind}'. Use one of: {', '.join(KINDS)}."
            )
        if "api_key" in entry:
            raise ConfigError(
                f"Provider '{name}' has an inline api_key. Keys belong in "
                f'{CREDENTIALS_PATH} or an environment variable — use auth = "env:VAR".'
            )

        providers[name] = ProviderConfig(
            name=name,
            kind=kind,
            model=entry.get("model") or KIND_DEFAULTS[kind]["model"],
            base_url=entry.get("base_url", ""),
            auth=entry.get("auth", ""),
            aws_region=entry.get("aws_region", DEFAULT_REGION),
            aws_profile=entry.get("aws_profile", ""),
        )
    return providers


def load_settings(repo_path: str | Path = ".") -> Settings:
    """Load global config, then overlay the project's, then env overrides.

    Precedence: env var > project > global. CLI flags are applied by the caller,
    which knows whether a flag was actually passed.
    """
    raw = _merge(
        _translate_legacy(_read_toml(GLOBAL_CONFIG_PATH)),
        _translate_legacy(_read_toml(Path(repo_path) / PROJECT_CONFIG_RELPATH)),
    )

    agent = raw.get("agent") or {}
    pricing = raw.get("pricing") or {}

    return Settings(
        providers=_build_providers(raw),
        default=os.environ.get("KADMON_PROVIDER", "") or raw.get("default", ""),
        mode=agent.get("mode", DEFAULT_MODE),
        max_iterations=agent.get("max_iterations", 50),
        pricing={k: float(v) for k, v in pricing.items() if k in ("input", "output")},
    )


def write_config(providers: list[ProviderConfig], default: str, path: Path = GLOBAL_CONFIG_PATH) -> None:
    """Write config.toml. Secrets are never written here."""
    # `default` must precede the tables: a bare key written after [providers.x]
    # would become part of that table, not the document root.
    lines = [
        "# Kadmon configuration",
        "# Generated by: kadmon init",
        "",
        f'default = "{default}"',
        "",
    ]
    for p in providers:
        lines.append(f"[providers.{p.name}]")
        lines.append(f'kind = "{p.kind}"')
        lines.append(f'model = "{p.model}"')
        if p.base_url:
            lines.append(f'base_url = "{p.base_url}"')
        if p.auth:
            lines.append(f'auth = "{p.auth}"')
        if p.kind == KIND_BEDROCK:
            lines.append(f'aws_region = "{p.aws_region}"')
            if p.aws_profile:
                lines.append(f'aws_profile = "{p.aws_profile}"')
        lines.append("")

    lines.append("[agent]")
    lines.append(f'mode = "{DEFAULT_MODE}"  # yolo | cautious | paranoid')
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def write_credential(name: str, api_key: str) -> None:
    """Store one API key in the credentials file, readable only by this user."""
    existing = _read_toml(CREDENTIALS_PATH) if CREDENTIALS_PATH.exists() else {}
    existing[name] = {"api_key": api_key}

    lines = ["# Kadmon credentials — keep private", ""]
    for entry_name, entry in existing.items():
        key = entry.get("api_key", "") if isinstance(entry, dict) else ""
        if key:
            lines.append(f"[{entry_name}]")
            lines.append(f'api_key = "{key}"')
            lines.append("")

    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_PATH.write_text("\n".join(lines))
    CREDENTIALS_PATH.chmod(0o600)
