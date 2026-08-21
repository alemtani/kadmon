# Adding a provider or OAuth

Two jobs. Do not mix them.

| Job | What you add | When |
| --- | --- | --- |
| **Provider** | An LLM transport (`kind`, factory, SDK) | A new completions host or SDK |
| **OAuth / subscription** | A `Vendor` in `kadmon/auth/` | Sign-in that draws from a subscription pool |

Grok already had a provider (`GrokProvider` + `kind = grok`). SuperGrok sign-in was a second job. Codex is the same split: OpenAI-compatible transport is likely already there; device-code sign-in is the vendor.

Bedrock and OpenRouter are **gateways**, not vendors. They route many models through one key. Do not model them as `kadmon login bedrock`. Track multi-model gateways later; do not block Grok or Codex on them.

## 1. Add an API-key provider

Use this when the user still pastes a key (or the SDK reads AWS, and so on).

1. Create `kadmon/providers/<name>.py` implementing `LLMProvider`.
2. Add `KIND_<NAME>` and `KIND_DEFAULTS` in `kadmon/config.py` (`model` + `env`).
3. Register a branch in `kadmon/providers/factory.py` `_build_llm`.
4. Put the kind in `discover()` if it should appear in `kadmon init`. Order is the init list. Bedrock stays last.
5. Tests with a mocked API. No network.

OpenAI-compatible hosts should subclass `OpenAIProvider`, not copy it. That class already owns 429 backoff and, through `GrantClient`, 401 refresh once a vendor exists.

`discover()` calls `_kind_candidate` for every key-based kind. If no vendor is registered yet, that helper falls through to the env var. You do not touch discovery again when you add OAuth for that kind.

## 2. Add OAuth for an existing kind (the smooth path)

Use this when the provider already exists (`grok`, `openai`, …) and you want `kadmon login <name>`.

Vendor `name` **must equal** the provider `kind`. Factory and discovery look up the registry by kind.

1. Create `kadmon/auth/<name>.py`. Subclass `Vendor`.
2. Implement `login(self, show)`. Call `show(LoginPrompt(...))` once if the user must open a URL or confirm a code. Return a `Grant`.
3. Override `refresh_grant` if the vendor issues refresh tokens. Use `kadmon.auth.oauth.post_form` / `is_dead_grant` for form-POST OAuth. Do not copy `xai.py` and swap URLs unless the endpoint is RFC 8628 with the same field names.
4. Override `pool_spent_message(status_code)` only when you have pinned that vendor’s exhaustion signal. Grok is 402. Do not guess.
5. Set `tested = False` until you have a real signed-in 200. Login then prints one experimental-path line.
6. Set `display_name`, `success_hint`, `run_notice`, `key_env` as needed.
7. Call `register(YourVendor())` in `kadmon/auth/__init__.py`.

Then:

- `kadmon login <name>` / `logout <name>` dispatch on their own.
- A live grant wins over the API key for that kind. `auth = "oauth:<name>"` is a record, not the switch.
- `init` shows “signed in as …” when a grant exists, or offers sign-in when it does not.
- 401 → `vendor.refresh_grant()` once → retry once → stop. HTTP blips do not clear the store.
- Completions host and identity headers stay on the **provider**. Grok pins `cli-chat-proxy.grok.com/v1` and CLI headers. An OpenAI-kind grant uses `OpenAIProvider` and never hits that proxy.

Claude is not this path. Anthropic does not give third-party Messages-API OAuth. Detect a local `claude` CLI later; do not invent device-code.

## 3. Add OAuth and a new kind together

When the vendor is not an existing kind (new name, new host):

1. Do section 1 for the kind (config, factory, provider class or `OpenAIProvider` reuse).
2. Add the kind to `_GRANT_KINDS` in `factory.py` so a grant is passed into that class.
3. Do section 2. `Vendor.name` matches the new kind.
4. If the kind is already in `KIND_DEFAULTS` but not in the `discover()` list, `_append_extra_vendors` inserts it before Bedrock once the vendor is registered.

## Checklist

- [ ] `Vendor.name` == provider `kind`
- [ ] `tested = False` until a real account has signed in
- [ ] Tokens only in `~/.config/kadmon/tokens.toml` (mode 0600). Extra keys round-trip.
- [ ] Refresh clears the grant only on `invalid_grant` / `invalid_token` / `revoked`
- [ ] Pool exhaustion never falls back to a key
- [ ] No `Authorization` in `default_headers` when `api_key` is set
- [ ] Offline tests: fake the token endpoint and the completions host
- [ ] `ruff check kadmon/ tests/` and `pytest tests/ -v`

## Where the code lives

| Piece | File |
| --- | --- |
| Vendor protocol, registry, `live(name)` | `kadmon/auth/vendor.py` |
| Token store | `kadmon/auth/store.py` |
| Shared form-POST OAuth | `kadmon/auth/oauth.py` |
| Grok device-code (reference implementation) | `kadmon/auth/xai.py` |
| 401 refresh + pool stop | `kadmon/providers/subscription.py` (`GrantClient`) |
| OpenAI-compatible transport | `kadmon/providers/openai_provider.py` |
| Grok proxy + CLI headers | `kadmon/providers/grok.py` |
| Grant-before-key | `kadmon/providers/factory.py` |
| Init detection | `kadmon/providers/discovery.py` |
| Spec | `docs/subscription-auth.md` |
