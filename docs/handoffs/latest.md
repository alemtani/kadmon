# Handoff: SuperGrok OAuth (sign in, don't paste a key)

## Read this first

Design: `docs/design/p1/provider-oauth.md` — reviewed nine times on
2026-08-19, ready to implement. Passes 2–6 each found real implementability
gaps in the pass before it; by pass 6 "The OAuth runtime" had accreted three
contradicting flags. Pass 7 collapsed those toward one boolean (`_committed`)
but over-collapsed: it conflated "can this call retry" with "can the run
switch credentials," which are actually independent (a later `complete()`
call in a healthy run can retry after a 401 even once `_committed`; a
`stream()` 401 after output already reached the display can never retry,
`_committed` or not). Pass 8 also found `init`'s grok branch can't see
`DeadGrantError` through `resolve_credentials()` (which catches it
internally), and that grok's key-fallback lookup can't use `config.auth`
(stuck at `"oauth:xai"` post-login, never rewritten except by `logout`).
Pass 9 found the interrupted-stream case pass 8 introduced had no delivery
path `AgentLoop._call_llm` could survive (stopping a stream with no `DONE`
crashes on `response.tool_calls`), and that 403 was handled three
inconsistent ways across the error tables, auth precedence, and init.

Fixed, this time with two independent mechanisms instead of one overloaded
flag: `_committed` (run-scoped, gates key fallback only) and `already_yielded`
(call-scoped, gates retry only — always `False` for `complete()`, resets
per `stream()` call). A new `StreamInterruptedError` (a `ConfigError`
subclass) covers the "healthy refresh, but this call's stream already sent
output" case, with `chat`'s REPL specifically staying open for it rather
than exiting. 403 is now `_committed`-gated the same way `DeadGrantError`
is — can fall through to a key before commitment, never after — instead of
being lumped with genuinely transient failures (timeout/5xx/429), and
`ConfigError` carries a `status_code` attribute so callers like `init` can
branch on it directly. `init`'s grok branch calls `load_tokens()`/
`refresh_tokens()` directly, never `resolve_credentials()`. The product
decision (device-code, xAI-only, file-only tokens) hasn't changed since
pass 1 — only the implementation-level specifics kept needing another pass,
each time by checking claims against this repo's actual code (this round:
`AgentLoop._call_llm`'s exact stream-consumption loop) instead of trusting
the previous pass's prose. If you're picking this up fresh: read "The OAuth
runtime" and "Error states" as they stand now, not as a history of what
they used to say.

Go/no-go: **go.** xAI's Grok CLI OAuth client (`b1a00492-073a-47ea-816f-4c329264a828`)
is public — confirmed in `grok-build`'s own test fixtures and reused openly by
several independent third-party OSS projects. Device-code flow, confirmed billing
(weekly SuperGrok pool, no separate charge). One correction to the original design:
OAuth traffic needs a different base URL (`cli-chat-proxy.grok.com/v1`, not
`api.x.ai/v1`) plus CLI-identity headers — see "Wire constants" and "The
credential contract" in the design doc. Read those sections before touching
`GrokProvider`; an adversarial review caught this doc contradicting itself on
that contract, storage, and status codes in an earlier pass — the current
version is the reconciled one.

**Current checkout note:** this working directory is on `main` right now, not
`feat/multi-provider`. The branch exists locally and on `origin` — check it
out before starting the implementation described here, since none of the
config/factory/GrokProvider code below exists on `main`.

## Where you are

Repo: `/Users/alemtani/projects/kadmon`
Branch: `feat/multi-provider` (PR https://github.com/ayuan153/kadmon/pull/2)

The PR already landed the config/factory work and a real `GrokProvider`:

- `kind = "grok"` (not `"openai"` + `base_url`)
- `kadmon/providers/grok.py` subclasses `OpenAIProvider`, pins `https://api.x.ai/v1`
- Default model `grok-4.6`, env `XAI_API_KEY`
- Ollama removed
- Init list order: Anthropic, OpenAI, xAI Grok, Gemini, Bedrock
- Init heading: `Providers ([✓] = credentials already on this machine)`

Latest commits on the branch (newest first):

- `a47bb81` fix(cli): order init providers by usage and clarify the list
- `e201675` feat(providers): add GrokProvider and drop Ollama
- `34ea301` feat(config): configure several providers at once, and add Grok

CI is red on `ruff check kadmon/ tests/` (~107 findings). This is ruff-version
drift (`ruff>=0.5.0` unbounded). `origin/main` fails the same check today (~112).
Local pytest: 383 passed. Not a Grok regression. Do not "fix CI" by rewriting
unrelated files unless the user asks.

## Why the next task exists

The user has SuperGrok ($30/month). Kadmon still demands `XAI_API_KEY` from
console.x.ai (separate pay-per-token bill). They called that BS. They are right
**for xAI**. They are not right as a universal claim: Claude Pro / ChatGPT Plus /
Gemini Advanced still do not give third-party agents a subscription OAuth token
for the developer API.

v1 is **xAI SuperGrok / X Premium+ sign-in**, API key as fallback.

## Current auth (what you will extend, not replace)

```
kadmon/config.py          ProviderConfig.auth = "env:VAR" | "credentials:name"
                          resolve_key() at use time, not at load
                          secrets in ~/.config/kadmon/credentials.toml mode 0600
kadmon/providers/factory.py  only place that constructs provider classes
kadmon/providers/grok.py     OpenAI-compatible; api_key is just a bearer secret
kadmon/cli.py init           if env key missing, prompt to paste, write_credential
tests/test_config.py         grok kind, XAI_API_KEY, factory, discovery order
tests/test_provider_wiring.py  AST guard: no direct Provider() outside factory
```

Proposed next auth source: `auth = "oauth:xai"`. `GrokProvider` still does not
own auth logic — it just gains a `headers` param — but it is not "dumb" about
endpoints anymore: it must accept a `base_url` that differs for OAuth vs. key
(see "The credential contract" in the design doc). An earlier note here said
"keep `GrokProvider` dumb," which undersold that change; the design doc's
credential-contract section is the current source of truth, not this line.

## What the last session decided (superseded where the design doc disagrees)

- Prefer OAuth where the vendor allows it. Keys stay.
- Do not scrape grok.com cookies.
- Do not boil the ocean. Grok only for v1.
- New command `kadmon login` / `logout` plus init offering sign-in first.
- Device-code only for v1 (SSH-friendly); browser PKCE is deferred, not
  "supported already" — an earlier note here called it "nicer on a laptop,"
  implying it ships too. It doesn't in v1.
- Token store: **file only** (`~/.config/kadmon/tokens.toml`, mode 0600,
  schema pinned in the design doc). An earlier note here said "keychain if
  cheap" — that's resolved now, no `keyring` dependency in v1.

## First actions in the new session

1. `git checkout feat/multi-provider` (see "Current checkout note" above).
2. Read `docs/design/p1/provider-oauth.md` end to end. The product decision
   (open questions 1–5) is settled — don't re-litigate xAI-only, device-code,
   or the client id. The implementation sections ("The credential contract"
   through "Standalone login") went through five rounds of adversarial
   review to close gaps earlier passes missed, including checks directly
   against this repo's real provider/agent/worker/CLI code; read them as the
   actual spec to code against, not as background. "The OAuth runtime" is
   now one state machine keyed on a single `_committed` flag (has this
   adapter produced real output yet this run) — every 401 goes through
   `refresh_tokens()` and is interpreted by what *that* reports, never
   treated as a dead grant directly. "The shared mapper" right before it
   pins `refresh_tokens()`'s `DeadGrantError`/`ConfigError` split, the
   corrected `interpret_http_error` signature, why the login-test path needs
   its own thin refresh-free wrapper, and the actual host+header predicate
   for classifying 402/426 as pool-exhaustion vs. a Kadmon bug.
3. Implement against AGENTS.md: lint `ruff check kadmon/ tests/` on files you
   touch, `pytest tests/ -v`, conventional commit. Cover the test cases listed
   under "Testing these from an intuitive standpoint" in the design doc (now
   34 cases, including the start-of-run vs. mid-run split for a dead session,
   the "revoked-but-not-yet-expired" gap between the 60-second margin and a
   real revocation, mid-run 401 on both `complete()` and `stream()` (with the
   stream case specifically covering a 401 arriving after a chunk was
   already yielded), standalone `login` with no prior `init`, `init`'s
   local-vs-networked `[✓]` split, the 402/426 predicate in both directions,
   and a case asserting non-grok providers never touch the OAuth path) — not
   just code-path coverage.

## How to resume the conversation with the user

They already know:

- SuperGrok ≠ API key
- Grok Build / Warp / OpenCode can sign in; Kadmon cannot
- They asked for thoughts, then a clean handoff, **not** code

Pick up with: the design doc is now reconciled after nine review passes (a
UX/rehash pass, then eight adversarial passes, the last several checked
directly against this repo's real code rather than the branch's claims). By
pass 9, the fixes had stopped being about missing pieces and started being
about the *shape* of the mechanism — pass 7's "one flag" collapse was the
right instinct but conflated two genuinely independent questions, and pass 9
untangled that into `_committed` (fallback) and `already_yielded` (retry) as
two separate, narrower mechanisms rather than one overloaded one. Go/no-go
is a firm **go**. What's left is implementation on `feat/multi-provider`,
not another design round. Nine passes is a lot for one spec — if a tenth
pass finds another decision issue in "The OAuth runtime" or "Error states"
specifically, that's worth raising with the user directly as a question of
whether continued review is still finding real gaps or diminishing returns,
rather than absorbing another silent fix.
