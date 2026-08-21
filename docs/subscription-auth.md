# Subscription sign-in

Kadmon uses the subscriptions you already pay for. An API key is a fallback.

This is the spec of record for sign-in. OAuth and evals are separate contexts.

## Problem

You pay SuperGrok. Kadmon still asks for `XAI_API_KEY` from
[console.x.ai](https://console.x.ai).

That key is a second meter. It bills pay-per-token. It is not your SuperGrok
pool.

You already paid $5 of API credit and spent $0.35 in one conversation. That is
not a way to run this agent.

The same split exists for Claude Pro/Max and for a Kimi coding plan. Those
subscriptions already drive coding agents. Kadmon should use them when they
exist.

Quote from the user: "OAuth should be a feature for all like including Claude,
no reason needed for the extra API key just rely on the sub if it exists."
Quote: "it's just the first thing that's needed for me to actually test this."

## Product rule

If a subscription can drive a coding agent, Kadmon uses it.

An API key is fallback. It is never the default when a live subscription
session exists.

Paste-key remains for three cases only:

- the vendor has no subscription path for a third-party agent
- the subscription session is dead or not entitled, and you choose a key
- you decline sign-in

A live subscription always wins over a key.

## Per vendor

| Vendor | What we do | What we will not do | Status |
| --- | --- | --- | --- |
| **xAI Grok** (SuperGrok / X Premium+) | Device-code sign-in. Usage draws from the SuperGrok weekly pool. File-only tokens (`~/.config/kadmon/tokens.toml`, mode 0600). Public Grok CLI client id `b1a00492-073a-47ea-816f-4c329264a828`. Signed-in completions go to `cli-chat-proxy.grok.com/v1` with CLI-identity headers, not `api.x.ai/v1`. OAuth runs against `auth.x.ai`. | Scrape grok.com cookies. Register a Kadmon-only OAuth client. Browser PKCE in this pass. | **v1.** Implement first, from current `main`. |
| **Anthropic Claude** (Pro / Max) | Detect the official `claude` CLI on this machine when it is logged in. Use it as a local subprocess for implementer or reviewer. Kadmon stays the agent (classifies, plans, routes). The CLI is model transport. | Copy `sk-ant-oat*` into Kadmon's HTTP client. Relay a token to a server. Log in as Claude for other people. Copy Grok device-code onto Anthropic. Call that path "OAuth." | **Later.** Blocked for native OAuth: Anthropic does not give third-party agents claude.ai OAuth for the Messages API. Subscription tokens used outside Claude Code have been rejected (Jan 2026+). Pro/Max is for the user's own individual use. |
| **Kimi** | Treat a membership coding-plan credential or a logged-in Kimi Code CLI as the subscription. | Pretend a quota key is OAuth if it is not. | **Later.** |
| **OpenAI** (ChatGPT Plus / Pro) | If an official CLI is installed and logged in, use it. If not, `kadmon init` says so in one line. | Fake "Sign in with ChatGPT" that still needs a console key. Send a consumer-sub token to the developer API. | **Blocked by vendor** for native third-party API. Official CLI is later, if it exists and is logged in. |
| **Google** (Gemini Advanced / Gemini CLI) | Same as OpenAI: official CLI if logged in; otherwise say so. | Fake "Sign in with Google" that still needs a Google AI Studio or Cloud key. | **Blocked by vendor** for native third-party API. Official CLI is later, if it exists and is logged in. |

## Sequencing

Vendors do not share an OAuth dance. They share the token store, `Grant`,
`AuthError`, and the `Vendor` registry so `kadmon login <name>` dispatches.

1. **Grok OAuth.** This is what blocks you from testing Kadmon at all. xAI
   supports device-code OAuth for third-party CLIs. SuperGrok pool. v1 is this
   path only. Do not re-open: xAI-only, device-code, file-only tokens, public
   client id.
2. **Claude-via-CLI.** Different mechanism. Not a copy-paste of Grok
   device-code. Not `kadmon/auth/xai.py` with a new issuer. Anthropic does not
   give Kadmon a Messages-API OAuth grant. The supported path is: `claude` is
   on PATH, this user already signed in, Kadmon subprocesses it locally.
3. **Kimi.** After Claude. Decide then whether the credential is a coding-plan
   key, a CLI, or both. Do not design it as Grok OAuth.

Signed-in Grok completions use xAI's CLI proxy (`cli-chat-proxy.grok.com/v1`),
not the console API host. That host serves completions, not the device-code or
token endpoints. Read `kadmon/providers/grok.py` before changing it.

Claude-via-CLI does not put an Anthropic token into `AnthropicProvider`. If
that provider still needs `ANTHROPIC_API_KEY`, the Claude subscription path is
not done.

## Auth precedence

The product rule needs a place to live in code. Today it has none.

`build_provider` calls `config.resolve_key()` before it builds the provider
(`kadmon/providers/factory.py:32`). `resolve_key` raises when it finds no key
and `base_url` is not localhost (`kadmon/config.py:79`). So a signed-in run
with no `XAI_API_KEY` fails at config resolve, before a provider exists.

Precedence at runtime, highest first:

1. A live grant for the provider's **kind** (the vendor name) in the token
   store. This wins on its own. Do not read `auth =` to reach it. Look the
   grant up with `kadmon.auth.live(kind)`, not a Grok-only helper.
2. The `auth =` spec — `env:VAR` or `credentials:name`.
3. Error, with one line on how to sign in or set a key.

`auth = "oauth:<vendor>"` is a **record** that `login` and `init` write so
`config.toml` shows where the credential came from. It is not the switch that
makes precedence work. A signed-in user whose config never gained that line
must still get rule 1. `oauth:` on a kind that is not that vendor is a config
error. An untested vendor must not drive a different kind's run.

Do not reuse `is_local` or the `"not-needed"` sentinel. Those exist for local
endpoints. They must not carry a subscription session.

### Cold start

A live grant must be enough to start from nothing. Two places ignore it today:

- `discovery.py:81` marks Grok available only when `XAI_API_KEY` is set. A
  signed-in user sees "XAI_API_KEY not set."
- `Settings.resolve` raises "No providers configured" (`kadmon/config.py:105`)
  when `config.toml` is absent, even with a live grant.

Discovery reads the token store. A live grant for a registered vendor makes
that vendor available and says so. `resolve` synthesises a provider from a
live grant when no config entry exists. If several tested vendors are signed
in and config names none, ask which one. An untested vendor is ignored when a
tested one (Grok) is also signed in.

### Host and headers

A live grant forces `cli-chat-proxy.grok.com/v1`. If `config.base_url` said
something else, override it and say so in one line. A live grant sent to
`api.x.ai/v1` bills the console meter — the same product failure as a silent
key fallback.

`cli-chat-proxy.grok.com/v1` is the **signed-in completions host**. It is not
the OAuth host. That is `auth.x.ai`. See "Spike results" below for both. The
freeze still holds: xAI-only, device-code, file tokens, public client id.

Carry the access token as `api_key`. `GrokProvider` already passes `api_key`
to `OpenAIProvider` (`kadmon/providers/grok.py:23`), and the SDK turns it into
`Authorization: Bearer`. `default_headers` carries CLI identity only. Never
put `Authorization` in `default_headers` — with `api_key` also set, that sends
two competing auth headers.

## Spike results

Done in PR 1. Source: the public Grok CLI 1.0.5 on this machine
(`~/.grok/bin/grok`), its OIDC discovery document, and its own traffic captured
by pointing `GROK_CLI_CHAT_PROXY_BASE_URL` at a local server. No secret was
read out of the CLI and none is recorded here.

**OAuth endpoints.** From `https://auth.x.ai/.well-known/openid-configuration`.
The same two paths are string constants in the CLI binary. High confidence.

| What | Value |
| --- | --- |
| Issuer | `https://auth.x.ai` |
| Device-code URL | `https://auth.x.ai/oauth2/device/code` |
| Token URL | `https://auth.x.ai/oauth2/token` |
| Grant type | `urn:ietf:params:oauth:grant-type:device_code` |
| Client id | `b1a00492-073a-47ea-816f-4c329264a828` |

The client id is confirmed twice: the spec pinned it, and the CLI records it as
`oidc_client_id` in `~/.grok/auth.json`. There is no client secret. The device
endpoint returns `verification_uri` `https://accounts.x.ai/oauth2/device` and a
`verification_uri_complete` that carries the user code.

**Scope.** High confidence that this set works. It was posted to the live
device-code endpoint and accepted:

```
openid profile email offline_access api:access grok-cli:access
conversations:read conversations:write workspaces:read workspaces:write
```

`team:read` and `org:read` are advertised but rejected for a personal account:
`Scope 'team:read' is not valid for User principals`. Do not ask for them.
Medium confidence that this string byte-matches the CLI's own default — the
scope names are all in the binary, but their order is not recoverable, and the
CLI does not record the granted scope on disk. Order does not matter to the
server.

**Token-request headers.** `content-type: application/x-www-form-urlencoded`
and nothing else. Confirmed: a bare form POST with only `client_id` and `scope`
returns 200. The binary hints that the CLI also sends
`x-grok-client-surface`, but the endpoint does not need it.

**CLI-identity headers.** Captured verbatim from the CLI's own request to the
signed-in completions host. High confidence.

| Header | Value |
| --- | --- |
| `x-grok-client-identifier` | `grok-shell` |
| `x-grok-client-version` | `1.0.5` (the CLI version) |
| `x-grok-client-mode` | `headless` for one-shot runs, `ui` interactively |
| `x-xai-token-auth` | `xai-grok-cli` |
| `user-agent` | `grok-shell/1.0.5 (macos; aarch64)` |

The CLI also sends `x-email`, `x-userid`, and per-turn ids (`x-grok-conv-id`,
`x-grok-session-id`, `x-grok-req-id`, `x-grok-turn-idx`). Those identify a
person and a conversation, not the client. Kadmon does not send them.

Note for PR 2: the CLI calls `POST /v1/responses` with SSE, not
`/v1/chat/completions`. `cli-chat-proxy.grok.com/v1/chat/completions` is a
string in the binary, so the proxy appears to serve both, but Kadmon's
chat-completions path over that host is **not** verified. Verify it in PR 2
before trusting it.

**Verified in PR 2: the proxy routes `/v1/chat/completions`.** An unauthenticated
`POST` to it returns 401 with the proxy's own auth error
(`Invalid or expired credentials (auth_kind=none, x_xai_token_auth=none, ...)`).
A path the proxy does not serve returns 404 instead — `/v1/chat/completionsX`
and `/v1/definitely-not-a-real-path` both do. `POST /v1/models` returns 405, so
the router answers per method as well. The route exists and reaches xAI's
auth check.

Still unverified: an authenticated 200 over that route. Getting one needs a real
token, and device-code sign-in needs a person at a browser. The chat-completions
transport is right; a live call is the first thing to watch when someone runs
`kadmon login grok` for real.

**Pool-exhaustion status code: 402.** The CLI's own strings pair
`run out of credits` with `status 402`, and a forced 402 renders as
`API error (status 402 Payment Required)` and stops — the CLI does not retry
it. So:

| Status | Meaning | Kadmon must |
| --- | --- | --- |
| 402 | Pool, credit, or spending cap spent | Stop or ask. Never fall back to a key |
| 403 | Not entitled / restricted | Start of run may offer a key. Mid-run, stop |
| 429 | Ordinary rate limit, transient | Retry, as `_call_with_retry` already does |
| 401 | Token rejected | Refresh once, retry once |

426 does not appear anywhere in the CLI. Write the U2 test against 402. Not
confirmed: whether an exhausted **weekly SuperGrok pool** specifically returns
402 rather than 429. The account used for the spike was not exhausted, so this
is inferred from the CLI's own error strings, not observed. If PR 2 can watch a
real exhaustion, confirm it then.

PR 2 could not watch one. The 402 is mocked in the tests and stays inferred.
The handling is built so a wrong inference is cheap: 402 stops, 429 keeps the
ordinary retry, and neither ever reaches for a key.

## Token lifecycle

Device-code OAuth returns an access token, an expiry, and a refresh token.
Storing them is not enough. Kadmon must keep them alive.

- **Before a run.** Refresh when the access token expires within 60 seconds.
- **During a run.** On a 401, refresh once and retry the call once. If the
  retry fails, stop.
- **On write.** Write to a temp file in the same directory, then `os.replace`.
  Re-apply mode 0600 after every write. Two Kadmon runs must not corrupt the
  store.
- **On refresh failure.** A rejected refresh token (`invalid_grant` and
  similar) is a dead grant. Clear it. A network or HTTP blip (5xx, 429,
  timeout) is not. Leave the grant in the store and raise. U2 lets a dead
  grant offer a key at the start of a run. An expired-but-refreshable token
  is neither. Never let it read as one.

`tokens.toml` schema, frozen. One table per vendor. Extra keys on a table
round-trip, so a Grok write cannot strip another vendor's fields.

```toml
[grok]
access_token = "..."
refresh_token = "..."
expires_at = 1755730000   # unix seconds
account = "..."           # what `login` prints back; may be empty
```

### Both call paths

Refresh, 401-retry-once, and the pool-exhaustion stop must run on `stream()`
as well as `complete()`.

`AgentLoop._call_llm` takes the stream branch whenever `display` is set
(`kadmon/agent/loop.py:392`). `chat` sets `display` (`kadmon/cli.py:152`), and
bare `kadmon` invokes `chat` (`kadmon/cli.py:98`). `run` does not
(`kadmon/cli.py:299`). `OpenAIProvider.stream` calls `chat.completions.create`
directly (`kadmon/providers/openai_provider.py:64`) and never enters
`_call_with_retry`.

So a test that drives only `complete()` can pass while the default `kadmon`
command 401s. At least one offline test must drive `stream()`.

## Usability checks

These are product acceptance checks. They are not eval scorecards.

**U1.** SuperGrok and Claude Pro can run Grok as implementer and Claude as
reviewer with **no API key in env or config at all**. No `XAI_API_KEY`. No
`ANTHROPIC_API_KEY`. No key in `~/.config/kadmon/credentials.toml`.

Grok OAuth alone does not pass U1. It does let you test Kadmon on SuperGrok
with no xAI console key. That is the v1 bar. U1 also needs Claude-via-CLI, and
a later way to assign implementer vs reviewer. Today one run binds one
`--provider`.

**U2.** If the subscription pool is exhausted, Kadmon stops or asks in one
line. It does not silently fall through to a pay-per-token key.

"Stops or asks" is not testable as written. The branch is the terminal, not
the command name:

- **TTY:** ask, in one line.
- **No TTY:** stop.

`eval` and `bench` are unattended and both build providers directly
(`kadmon/eval/polyglot.py:456`, `kadmon/eval/harness.py:57`). The factory and
the provider must never prompt. The CLI may prompt around `_make_provider` —
it already builds `CLIChannel` itself (`kadmon/cli.py:128`, `:252`), so this
is not a layering problem.

For Grok, a well-formed 402 is pool exhaustion. See "Spike results". 426 does
not occur; drop it. `GrokProvider` inherits `_call_with_retry` from
`OpenAIProvider`, which retries a 429 three times and then raises. A 429 from
this proxy is an ordinary rate limit, so that retry is right. Do not widen it
to 402.

A dead grant or a 403-not-entitled at the **start** of a run may still offer a
key, with a visible notice. Do not treat pool exhaustion as a dead grant.
Mid-run, a 403 stops the run; it never offers a key. A key accepted at the
prompt applies to that run only. Writing it to `credentials.toml` needs a
separate, explicit yes.

Claude-via-CLI and Kimi must follow U2 as well. A Claude usage cap must not
silently move the call onto `ANTHROPIC_API_KEY`.

## What the user sees (Grok v1)

Every row is a state a real person reaches. No two rows may render the same.

| State | What Kadmon shows | Falls back to a key? |
| --- | --- | --- |
| `kadmon init`, no key, not signed in | Offers Grok sign-in first, key second | Only if you decline |
| `kadmon init`, live grant, no key | "xAI Grok — signed in." Never prompts for a console key | No |
| `kadmon login grok` | Verification URL and user code, then waits | — |
| You deny, or the code expires | One line: what happened, how to retry | No |
| `kadmon login grok`, already signed in | Says you are signed in and to which account. Does **not** re-render as signed out | No |
| Run, signed in, no config file at all | Runs. A grant is enough to start from nothing | No |
| Run, signed in, no key anywhere | Runs. Says the run is on your SuperGrok pool | No |
| Run, signed in, `XAI_API_KEY` also set | Runs on the subscription. Says so in one line, and names the key it ignored | No |
| Run, signed in, config sets another `base_url` | Uses the proxy host. One line: the configured `base_url` was overridden | No |
| Access token expired, refresh works | Nothing. The run continues | No |
| Refresh fails at start, TTY | One line: signed out. Offers a key with a visible notice | Yes, that run only |
| Refresh fails at start, no TTY (`eval`, `bench`) | Stops. One line | No |
| Refresh fails mid-run | Stops. One line: sign in again | No |
| Weekly pool exhausted, TTY | Asks, in one line | **Never** |
| Weekly pool exhausted, no TTY | Stops, in one line | **Never** |
| 403 not entitled, start of run, TTY | One line. Offers a key with a visible notice | Yes, that run only |
| `kadmon logout grok` | Confirms the token is gone | — |

Pool exhaustion and a dead grant must never share wording. One means wait. The
other means sign in again. A user who cannot tell them apart will reach for a
key and start paying per token.

## Test cases

Written from what a person hits, in the order they hit it. All are offline —
fake the token endpoint and the proxy. Names map to the rows above.

**Happy path**

1. `login_grok_stores_token` — device-code flow completes, `tokens.toml`
   exists, mode is 0600, schema matches.
2. `run_signed_in_needs_no_key` — U1's Grok half. No `XAI_API_KEY` in env, no
   `credentials.toml`. The run builds a provider and calls the proxy host.
3. `cold_start_grant_only` — no `config.toml` at all. Discovery marks Grok
   available and `resolve` does not raise "No providers configured."
4. `init_with_live_grant_never_prompts_for_key` — `kadmon init`, grant live.
   No key prompt, and `credentials.toml` is not written.
5. `logout_grok_removes_token` — after logout, the store holds no Grok grant.

**Failure modes a user actually meets**

6. `expired_token_refreshes_silently` — the run produces no extra output.
7. `dead_grant_at_start_offers_key_on_tty` — the notice is visible and names
   the trade. The key is not persisted without a second yes.
8. `dead_grant_no_tty_stops` — `eval` and `bench` never prompt.
9. `dead_grant_midrun_stops` — no key fallback, no silent retry loop.
10. `pool_exhausted_never_falls_back_to_key` — a 402 stops the run even
    when `XAI_API_KEY` is set and valid. This is the U2 regression guard.
11. `pool_exhaustion_and_dead_grant_differ` — assert the two messages are not
    equal. Guards the identical-render failure above.
12. `login_when_already_signed_in_says_so` — output differs from the
    signed-out case.

**Precedence and transport**

13. `subscription_beats_key` — both present, the proxy host is called, and the
    output names the ignored key.
14. `key_only_uses_console_host` — not signed in, `XAI_API_KEY` set, traffic
    goes to `api.x.ai/v1`.
15. `grant_overrides_configured_base_url` — config sets `api.x.ai/v1`, grant
    is live, the proxy host wins and the override is announced.
16. `no_duplicate_auth_header` — the token rides as `api_key`;
    `default_headers` holds no `Authorization`.
17. `stream_path_refreshes_and_stops` — drives `stream()`, not `complete()`.
   Covers refresh-once, 401-retry-once, and the pool-exhaustion stop.

## Adding a vendor

Walkthrough: `docs/adding-a-provider.md`. Provider transport and OAuth are
separate jobs. Short form for OAuth on an existing kind:

1. Subclass `kadmon.auth.Vendor` in `kadmon/auth/<name>.py`. `name` must equal
   the provider `kind`. Implement `login`. Override `refresh_grant` if the
   vendor refreshes tokens. Override `pool_spent_message` if you have pinned
   that host's spent-pool status.
2. Set `tested = False` until the live endpoints are verified. Login then
   prints one experimental-path line. OpenAI, Codex, and anything else we have
   not run against a real account stay in this state.
3. Call `register(YourVendor())` in `kadmon/auth/__init__.py`.

Do not copy `xai.py` and swap URLs unless the vendor is RFC 8628 device-code
with the same field names. Claude is a local CLI, not this class of flow.
Bedrock and OpenRouter are gateways, not `kadmon login` vendors.

A run reads the grant with `kadmon.auth.live(kind)`, not
`kadmon.auth.xai.live_grant`. Completions host and identity headers stay on
the provider — do not reuse SuperGrok's proxy. Discovery already uses
`_kind_candidate`, which falls through to the env var when no vendor is
registered.

## Pointers

| What | Where |
| --- | --- |
| How to add a provider or OAuth | `docs/adding-a-provider.md` |
| Code to extend | `kadmon/auth/`, `kadmon/config.py`, `kadmon/providers/factory.py`, `kadmon/providers/grok.py`, `kadmon/providers/discovery.py`, `kadmon/providers/openai_provider.py`, `kadmon/cli.py` |

Implement Grok login from current `main` on this fork (`alemtani/kadmon`), on a
new branch. PR #2 already merged `GrokProvider` and the factory. There is no
`kadmon login`. There is no `kadmon/auth/`. Auth is still `env:VAR` or
`credentials:name` only.

## Open questions

Settled for Grok v1 — do not re-open: xAI-only, device-code, file-only
`~/.config/kadmon/tokens.toml` mode 0600, public client id
`b1a00492-073a-47ea-816f-4c329264a828`, signed-in completions host
`cli-chat-proxy.grok.com/v1`.

Pinned by the spike, not open for design: the device-code URL, the token URL,
the scope, the token-request headers, the CLI-identity headers, and the
pool-exhaustion status code. All are recorded in "Spike results" above. Two
things there are inferred, not observed, and PR 2 must confirm them: that the
proxy serves `/v1/chat/completions`, and that an exhausted weekly pool returns
402 rather than 429.

Still open (none of these block Grok v1):

1. **U1 routing.** A run today binds one provider. How does a later Task set
   Grok as implementer and Claude as reviewer? Design this with
   Claude-via-CLI, not during Grok login.
2. **Claude subprocess contract.** How Kadmon talks to `claude` (argv, stream
   vs print, tools, cwd, timeout, failure copy). Not a Grok adapter with a
   different URL. Design when step 2 starts.
3. **`kadmon login claude` vs detect.** The user may already have run
   `claude` login. Detection may be enough. Do not invent a device-code flow
   Anthropic does not offer.
4. **Kimi credential shape.** Coding-plan key, Kimi Code CLI, or both. Decide
   when Kimi is next.

## First actions (Grok login)

Two PRs. The first is testable on its own.

**PR 1 — auth core.**

1. Branch from `main` on `alemtani/kadmon`. Do not commit to `main`.
2. Spike first: pin the device-code URL, token URL, scope, token-request
   headers, CLI-identity headers, and the pool-exhaustion status code. Record
   them in this doc. **Done** — see "Spike results".
3. Add `kadmon/auth/`: vendor-keyed store, `Vendor` registry, Grok
   device-code in `xai.py`.
4. Store tokens in `~/.config/kadmon/tokens.toml` mode 0600, schema above.
   Atomic write via temp file plus `os.replace`, re-chmod every write.
5. Add `kadmon login grok` and `kadmon logout grok`. Login on an existing
   grant must not render as signed out.
6. Tests 1, 5, 6, 12 from the list above. Fake the token endpoint. No network.

**PR 2 — wire it in.**

1. Branch from PR 1. Do not commit to `main`.
2. Precedence in `kadmon/config.py` and `kadmon/providers/factory.py`:
   `kind == grok` plus a live grant wins before `resolve_key` runs.
   `auth = "oauth:grok"` is a record only. `oauth:` on a non-grok kind errors.
3. Cold start: `discovery.py` reads the token store; `Settings.resolve`
   synthesises a Grok provider from a live grant.
4. `GrokProvider` splits transport. A live grant forces
   `cli-chat-proxy.grok.com/v1` and announces any `base_url` override. Token
   rides as `api_key`; `default_headers` is CLI identity only.
5. Refresh, 401-retry-once, and the pool-exhaustion stop on **both**
   `complete()` and `stream()`.
6. U2 branch: TTY asks, no TTY stops. The factory and the provider never
   prompt. The CLI prompts around `_make_provider`.
7. Init offers sign-in first and never prompts for a key while a grant is
   live. Note that `_test_provider` (`kadmon/cli.py:694`) makes a live
   `complete()` call, so setup spends pool. Use a cheaper check.
8. Remaining tests: 2, 3, 4, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17.

Both PRs: lint files you touch. Add tests. Conventional commits, e.g.
`feat(providers): sign in to SuperGrok with device-code OAuth`.
