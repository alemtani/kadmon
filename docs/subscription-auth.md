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
| **xAI Grok** (SuperGrok / X Premium+) | Device-code sign-in. Usage draws from the SuperGrok weekly pool. File-only tokens (`~/.config/kadmon/tokens.toml`, mode 0600). Public Grok CLI client id `b1a00492-073a-47ea-816f-4c329264a828`. OAuth calls go to `cli-chat-proxy.grok.com/v1` with CLI-identity headers, not `api.x.ai/v1`. | Scrape grok.com cookies. Register a Kadmon-only OAuth client. Browser PKCE in this pass. | **v1.** Implement first, from current `main`. |
| **Anthropic Claude** (Pro / Max) | Detect the official `claude` CLI on this machine when it is logged in. Use it as a local subprocess for implementer or reviewer. Kadmon stays the agent (classifies, plans, routes). The CLI is model transport. | Copy `sk-ant-oat*` into Kadmon's HTTP client. Relay a token to a server. Log in as Claude for other people. Copy Grok device-code onto Anthropic. Call that path "OAuth." | **Later.** Blocked for native OAuth: Anthropic does not give third-party agents claude.ai OAuth for the Messages API. Subscription tokens used outside Claude Code have been rejected (Jan 2026+). Pro/Max is for the user's own individual use. |
| **Kimi** | Treat a membership coding-plan credential or a logged-in Kimi Code CLI as the subscription. | Pretend a quota key is OAuth if it is not. | **Later.** |
| **OpenAI** (ChatGPT Plus / Pro) | If an official CLI is installed and logged in, use it. If not, `kadmon init` says so in one line. | Fake "Sign in with ChatGPT" that still needs a console key. Send a consumer-sub token to the developer API. | **Blocked by vendor** for native third-party API. Official CLI is later, if it exists and is logged in. |
| **Google** (Gemini Advanced / Gemini CLI) | Same as OpenAI: official CLI if logged in; otherwise say so. | Fake "Sign in with Google" that still needs a Google AI Studio or Cloud key. | **Blocked by vendor** for native third-party API. Official CLI is later, if it exists and is logged in. |

## Sequencing

Do not wait for a shared OAuth layer. The vendors do not offer the same door.

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

Signed-in Grok traffic uses xAI's CLI proxy (`cli-chat-proxy.grok.com/v1`),
not the console API host. Read `kadmon/providers/grok.py` before changing it.

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

For Grok, a well-formed 402/426 is weekly-pool exhaustion: stop or ask in
one line. Do not silently switch to a key. A dead grant or a
403-not-entitled at the **start** of a run may still offer a key, with a
visible notice. Do not treat pool exhaustion as a dead grant.

Claude-via-CLI and Kimi must follow U2 as well. A Claude usage cap must not
silently move the call onto `ANTHROPIC_API_KEY`.

## Pointers

| What | Where |
| --- | --- |
| Code to extend | `kadmon/config.py`, `kadmon/providers/factory.py`, `kadmon/providers/grok.py`, `kadmon/cli.py` |

Implement Grok login from current `main` on this fork (`alemtani/kadmon`), on a
new branch. PR #2 already merged `GrokProvider` and the factory. There is no
`kadmon login`. There is no `kadmon/auth/`. Auth is still `env:VAR` or
`credentials:name` only.

## Open questions

Settled for Grok v1 — do not re-open: xAI-only, device-code, file-only
`~/.config/kadmon/tokens.toml` mode 0600, public client id
`b1a00492-073a-47ea-816f-4c329264a828`, OAuth host `cli-chat-proxy.grok.com/v1`.

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

1. Branch from `main` on `alemtani/kadmon`. Open a PR. Do not commit to `main`.
2. Add `kadmon login grok` / `kadmon logout grok` (device-code). Store tokens
   in `~/.config/kadmon/tokens.toml` mode 0600. Init offers sign-in first.
3. OAuth traffic uses `cli-chat-proxy.grok.com/v1` and CLI-identity headers.
   Key traffic still uses `api.x.ai/v1`.
4. Pool exhausted (402/426): one-line stop or ask. No silent key fallback.
5. Lint files you touch. Add tests. Conventional commit, e.g.
   `feat(providers): sign in to SuperGrok with device-code OAuth`.
