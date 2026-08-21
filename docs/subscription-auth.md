# Subscription sign-in

Kadmon uses the subscriptions you already pay for. An API key is a fallback.

This is the product and sequencing brief. Grok wire-level detail lives in
[`docs/design/p1/provider-oauth.md`](design/p1/provider-oauth.md). Do not copy
it here.

OAuth and subscription auth are a separate context from evals.

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
| **xAI Grok** (SuperGrok / X Premium+) | Device-code sign-in. Usage draws from the SuperGrok weekly pool. File-only tokens. Public Grok CLI client id. | Scrape grok.com cookies. Register a Kadmon-only OAuth client (xAI has no public registration). Browser PKCE in this pass. | **v1.** Design is ready. Implement first. Spec: [`docs/design/p1/provider-oauth.md`](design/p1/provider-oauth.md). |
| **Anthropic Claude** (Pro / Max) | Detect the official `claude` CLI on this machine when it is logged in. Use it as a local subprocess for implementer or reviewer. Kadmon stays the agent (classifies, plans, routes). The CLI is model transport. | Copy `sk-ant-oat*` into Kadmon's HTTP client. Relay a token to a server. Log in as Claude for other people. Copy Grok device-code onto Anthropic. Call that path "OAuth." | **Later.** Blocked for native OAuth: Anthropic does not give third-party agents claude.ai OAuth for the Messages API. Subscription tokens used outside Claude Code have been rejected (Jan 2026+). Pro/Max is for the user's own individual use. |
| **Kimi** | Treat a membership coding-plan credential or a logged-in Kimi Code CLI as the subscription. | Pretend a quota key is OAuth if it is not. | **Later.** |
| **OpenAI** (ChatGPT Plus / Pro) | If an official CLI is installed and logged in, use it. If not, `kadmon init` says so in one line. | Fake "Sign in with ChatGPT" that still needs a console key. Send a consumer-sub token to the developer API. | **Blocked by vendor** for native third-party API. Official CLI is later, if it exists and is logged in. |
| **Google** (Gemini Advanced / Gemini CLI) | Same as OpenAI: official CLI if logged in; otherwise say so. | Fake "Sign in with Google" that still needs a Google AI Studio or Cloud key. | **Blocked by vendor** for native third-party API. Official CLI is later, if it exists and is logged in. |

## Sequencing

Do not wait for a shared OAuth layer. The vendors do not offer the same door.

1. **Grok OAuth.** This is what blocks you from testing Kadmon at all. xAI
   supports device-code OAuth for third-party CLIs. SuperGrok pool. v1 is this
   path only. Implement against the Grok spec. Do not re-open product decisions
   1–5 in that file (xAI-only, device-code, file-only tokens, public client id).
2. **Claude-via-CLI.** Different mechanism. Not a copy-paste of Grok
   device-code. Not `kadmon/auth/xai.py` with a new issuer. Anthropic does not
   give Kadmon a Messages-API OAuth grant. The supported path is: `claude` is
   on PATH, this user already signed in, Kadmon subprocesses it locally.
3. **Kimi.** After Claude. Decide then whether the credential is a coding-plan
   key, a CLI, or both. Do not design it as Grok OAuth.

Signed-in Grok traffic uses xAI's CLI proxy, not the console API host. The
Grok spec pins the host and headers. Read that file before touching
`GrokProvider`.

Claude-via-CLI does not put an Anthropic token into `AnthropicProvider`. If
that provider still needs `ANTHROPIC_API_KEY`, the Claude subscription path is
not done.

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

For Grok, the spec already maps well-formed 402/426 to the weekly-pool
message and forbids a key switch on that path. Keep that. A dead grant or a
403-not-entitled at the **start** of a run may still offer a key, with a
visible notice, as that spec already decided. Do not reopen those rows. Do
not treat pool exhaustion as a dead grant.

Claude-via-CLI and Kimi must follow U2 as well. A Claude usage cap must not
silently move the call onto `ANTHROPIC_API_KEY`.

## Pointers

| What | Where |
| --- | --- |
| Grok implementation spec (wire, errors, adapter, tests) | [`docs/design/p1/provider-oauth.md`](design/p1/provider-oauth.md) |
| Grok implementer handoff | [`docs/handoffs/latest.md`](handoffs/latest.md) |
| Code to extend | `kadmon/config.py`, `kadmon/providers/factory.py`, `kadmon/providers/grok.py`, `kadmon/cli.py` |

**Branch fact, 2026-08-20.** PR
[#2](https://github.com/ayuan153/kadmon/pull/2) (`feat/multi-provider`) merged
to `main` as `4aeebf1`. GitHub deleted the remote branch. This checkout is
`main`. `main` already has `ProviderConfig`, `resolve_key()`, `factory.py`, and
`GrokProvider`. The Grok spec's 2026-08-19 note that `main` lacks those files
is stale. Implement Grok login from current `main`, on a new branch. A local
`feat/multi-provider` ref may still sit at `a47bb81`; do not treat it as the
parent.

OAuth has not shipped. There is no `kadmon login`. There is no
`kadmon/auth/`. Auth is still `env:VAR` or `credentials:name` only.

## Open questions

Settled for Grok v1 — do not re-open: xAI-only, device-code, file-only
`~/.config/kadmon/tokens.toml` mode 0600, public client id
`b1a00492-073a-47ea-816f-4c329264a828`. See the Grok spec, "Open questions —
resolved 2026-08-19."

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

## First actions (Grok login, next session)

Do not re-read the success-criteria thread. This list is enough to start.

1. Create a new branch from current `main`. PR #2 is already merged. Do not
   start from `origin/feat/multi-provider`.
2. Read [`docs/design/p1/provider-oauth.md`](design/p1/provider-oauth.md) end
   to end. Code against "The credential contract", "The OAuth runtime",
   "Error states", "Auth precedence", and "Standalone login". Product
   decisions 1–5 stay closed.
3. Use **two** mechanisms, not one. `_committed` (run-scoped) gates key
   fallback. `already_yielded` (call-scoped) gates retry. A later
   `complete()` 401 in a healthy run can retry. A `stream()` 401 after a
   yielded chunk cannot. The handoff's "one `_committed` flag" sentence is
   stale. The design doc wins.
4. Add `kadmon/auth/xai.py` (`device_login`, `load_tokens`, `refresh_tokens`,
   `save_tokens`, `clear_tokens`). Rename `resolve_key()` to
   `resolve_credentials()`; OAuth lookup is grok-only. Add `headers` on
   `OpenAIProvider` and `GrokProvider`. Wrap live OAuth only in
   `XAIRefreshAdapter` inside `factory.py`. Add `kadmon login grok` and
   `kadmon logout grok`. Init's grok branch calls `load_tokens()` /
   `refresh_tokens()` directly, never `resolve_credentials()`.
5. Lint the files you touch (`ruff check kadmon/ tests/`). Cover the 34 cases
   under "Testing these from an intuitive standpoint" in the Grok spec.
   Conventional commit, e.g. `feat(providers): sign in to SuperGrok with
   device-code OAuth`.
