# Provider sign-in (OAuth) instead of pasted API keys

Status: reviewed seven times. Pass 1 was a UX/research rehash. Passes 2–6
were successive adversarial reviews, each finding real implementability gaps
in the pass before it (contradictory credential contract; an error table
with indistinguishable rows and no named runtime module; an auth path not
gated to Grok; an unpinned wrap boundary and error-delivery mechanism; a
mapper signature that couldn't cover every caller). By pass 6, "The OAuth
runtime" had accreted a `_first_call_done` flag, a separate stream-yield
rule, and a construction-time refresh check — three special cases patched
in across three passes, two of which contradicted each other (a plain
inference 401 was being treated as a dead grant directly, and the flag and
the stream-yield rule disagreed about which 401s were retryable). Pass 7
diagnosed that as a sign of solving the wrong-shaped problem and collapsed
it toward one boolean, but over-collapsed: it conflated two independent
questions — can *this call* be retried, and can the run still switch
credentials — into one `_committed` flag, which is wrong for the case where
a later `complete()` call in an otherwise-healthy run 401s (retryable) vs. a
`stream()` 401 arriving after output already reached the display (never
retryable), both of which have `_committed == True`. Pass 8 also found:
`kadmon init`'s grok branch can't observe `DeadGrantError` if it validates
through `resolve_credentials()` (which catches that exception internally);
grok's key-fallback lookup can't go through `config.auth`, because `auth`
gets stuck at `"oauth:xai"` after any successful login and nothing rewrites
it back; and the OAuth rebuild on a healthy refresh needs to keep
`XAI_OAUTH_BASE_URL`/`XAI_OAUTH_HEADERS`, not just the new token, or a
routine refresh would send OAuth traffic to the API-key host. Pass 9 found
the interrupted-stream case pass 8 introduced (a 401 after a chunk was
already yielded, but the grant is actually fine) had no delivery path
`AgentLoop._call_llm` can survive — stopping a stream with no `DONE` chunk
crashes on `response.tool_calls`, and synthesizing a fake `DONE` would be a
streaming-contract change — and that 403 was being treated three
inconsistent ways across the error table, auth precedence, and init. Fixed:
**two independent mechanisms**, `_committed` (run-scoped, gates key
fallback) and `already_yielded` (call-scoped, gates retry); a new
`StreamInterruptedError` (a `ConfigError` subclass) for the interrupted-but-
healthy stream case, with `chat`'s REPL specifically staying open for it
instead of exiting; 403 is now `_committed`-gated exactly like `DeadGrantError`
(can fall through to a key before commitment, never after) instead of being
lumped with genuinely transient failures; `ConfigError` now carries a
`status_code` attribute so callers like `init` can branch on it without
parsing message text; and `init`'s grok branch calls `load_tokens()`/
`refresh_tokens()` directly, never `resolve_credentials()`. Ready to
implement against `feat/multi-provider`.

Ergonomics, not a new model. `kadmon init` should prefer "sign in" where the vendor
allows it. Pasted API keys stay as a fallback.

## Why this exists

Kadmon currently treats every cloud provider as a secret string:

- `auth = "env:XAI_API_KEY"` or `auth = "credentials:grok"`
- `ProviderConfig.resolve_key()` reads that string
- `build_provider` passes it to the SDK as `api_key`

That is the lowest-common-denominator path. It is also the worst path for a user
who already pays for the product.

The concrete pain: SuperGrok is $30/month for grok.com / Grok Build. Kadmon still
asks for an `XAI_API_KEY` from [console.x.ai](https://console.x.ai), which is a
**separate, pay-per-token bill**. The same model, two checkouts.

xAI already lets first-party and partnered agents skip the key:

- Grok Build CLI — `curl -fsSL https://x.ai/cli/install.sh | bash`, then browser login
- Warp — SuperGrok OAuth, usage against the weekly SuperGrok pool
- OpenCode — official xAI post: "Use your SuperGrok or X Premium subscription"
- Hermes Agent — device-code OAuth, printing a verification URL under
  `accounts.x.ai` (the human-facing domain the user visits) while the actual
  token requests go to `auth.x.ai` (the API host) — see "Wire constants" for
  both, they're not interchangeable

Kadmon is a third-party CLI that only speaks the public API. That is a product gap,
not a law of physics.

## What this is not

- Not scraping grok.com cookies. Fragile and against terms.
- Not "delete API keys from the codebase." Keys remain the fallback and the only
  path for vendors that do not offer third-party OAuth.
- Not a promise that Claude Pro, ChatGPT Plus, or Gemini Advanced will work the
  same way. Those consumer plans still do not, as of 2026-08, give a public OAuth
  token that third-party agents can send to the developer API.

xAI is the wedge because they actually opened subscription OAuth. Other vendors
plug into the same `auth` slot later if they do the same.

## Target UX

```
$ kadmon init

Providers ([✓] = already signed in or keyed):
  [ ] 1. Anthropic
  [ ] 2. OpenAI
  [ ] 3. xAI Grok
  [ ] 4. Google Gemini
  [ ] 5. AWS Bedrock

Providers [3]:

xAI Grok
  Sign in with SuperGrok / X Premium+? [Y/n]:
  Visit https://accounts.x.ai/device and enter code ABCD-1234
  Signed in as you@x.ai (from the id_token). Usage draws from your SuperGrok
  weekly pool.
```

v1 is device-code only — see "Wire constants" below. No local browser flow
ships in this pass, so init always prints a device code rather than opening one.

Headless:

```
$ kadmon login grok
Visit https://accounts.x.ai/device and enter code ABCD-1234
```

API key still works: `export XAI_API_KEY=...` or paste during init if they decline
sign-in.

### Error states — two tables, because "session ended" means different things at different times

A user who signs in should see the same kind of clear, one-line feedback
whether things go right or wrong. Earlier drafts had **one** table and it
quietly described two different products: at the start of a run, a dead
OAuth session can fall through to an API key with a visible notice; mid-run,
after the retry adapter's one refresh+retry has already failed, it must
**not** — switching which account authorized a request invisibly, partway
through a run, is worse than stopping. Same underlying signal
(`invalid_grant`/401), two different, non-overlapping behaviors depending on
*when* it happens. Splitting the table removes the ambiguity a single row
couldn't hold:

**A. Login and start-of-run** (device-code flow; `build_provider`'s one-time
token check before any inference request this run):

| Signal | Action | User sees |
| --- | --- | --- |
| `authorization_pending` | Keep polling at the current interval | (nothing yet — still waiting) |
| `slow_down` | Add 5s to the interval, keep polling | (nothing yet — still waiting) |
| `expired_token`, or the poll ran past `expires_in` | Stop | `Code expired. Run \`kadmon login grok\` again.` |
| `access_denied` | Stop | `Sign-in was denied. Run \`kadmon login grok\` to try again.` |
| Refresh returns HTTP 401 or JSON `invalid_grant` — a "dead grant," discoverable either here (at construction time) or via the adapter's own `refresh_tokens()` call on a first-call inference 401 (see "The OAuth runtime") — both routes agree on what "dead" means | Clear the stored `[xai]` entry. If the grok-only key lookup (see "Auth precedence") finds a key, fall through to it | `Signed-in xAI session ended; using your XAI_API_KEY instead.` If no key is available instead: `Signed-in xAI session ended. Run \`kadmon login grok\` to sign in again, or set XAI_API_KEY.` |
| Refresh returns 403 at start of run (well-formed request) | Keep the token — same as table B's 403 row, not a dead grant | The not-entitled message (table B) |
| Refresh times out, or returns 5xx/429 at start of run | Keep the token — this is a **transient failure, not a dead grant**, and must not be treated as one | `Couldn't reach xAI to check your session. Check your connection and try again.` |
| No `[xai]` entry and no key resolves | Stop | `xAI Grok isn't configured. Run \`kadmon login grok\` to sign in, or set XAI_API_KEY.` |

The transient-failure row exists because an earlier draft only named 401/`invalid_grant` as the fall-through trigger and left every other refresh failure unspecified. A writer who treats *any* refresh exception (a timeout, a 500, a rate limit) as a dead grant would clear a perfectly good token and silently switch to `XAI_API_KEY` on a network blip — exactly the identity-switch table B's mid-run rule exists to prevent, just relocated to the start of the run. **Dead grant means *only* what `refresh_tokens()` itself reports** (HTTP 401 or JSON `invalid_grant` *from a refresh call*) — never the raw fact that an inference request 401'd. A plain inference 401 is not, by itself, evidence the grant is dead; it's evidence to go check, by calling `refresh_tokens()`. This matters because a dead grant discovered *before* the access token's own 60-second margin (i.e. via a first inference call, not via this table's construction-time check) is exactly as much a "start of run" event as this table's own row — see "The OAuth runtime" below for the one mechanism that handles both, so this table's row and that mechanism can't quietly diverge on what "dead grant" means the way an earlier pass let them.

**B. Mid-run** (the retry adapter below — a token that was good when the run
started but died partway through):

| Signal | Action | User sees |
| --- | --- | --- |
| Inference 401, first occurrence this call, **and this call hasn't already yielded output** (always true for `complete()`; true for `stream()` only before its first chunk) | Refresh once, retry the same call once | (nothing yet — transparent) |
| Inference 401 again, after that one retry | Stop. **Never** fall through to `XAI_API_KEY` here, even if it's set | `Signed-in xAI session ended partway through this run. Run \`kadmon login grok\` to sign in again, or set XAI_API_KEY and re-run.` |
| Inference 401 on a `stream()` call that **already yielded a chunk**, refresh succeeds | Do not retry (deduping partial output is out of scope) — the session is fine, only this call's connection dropped | `Connection interrupted partway through the response. Your session is fine — try your last message again.` (a distinct `StreamInterruptedError`, not the "session ended" copy — see "The OAuth runtime") |
| Inference 401 on a `stream()` call that already yielded a chunk, refresh instead raises `DeadGrantError` | Stop, same as the plain mid-run row above — the grant really is dead, unrelated to the interrupted connection | `Signed-in xAI session ended partway through this run. Run \`kadmon login grok\` to sign in again, or set XAI_API_KEY and re-run.` |
| Inference or refresh 403, **not yet committed this run** (no earlier call succeeded, no chunk yielded yet) | Keep the token (never `clear_tokens()` — a 403 isn't a dead grant). Same mechanism as the `DeadGrantError`-with-key branch above: if the grok-only key lookup finds a key, **swap the adapter's delegate to a plain, unwrapped `GrokProvider` built from that key**, `emit_auth_notice()`, retry the same call on the new delegate, then the adapter is inert for the rest of the process (no more OAuth logic at all this run) — retrying the *same OAuth call* again would just 403 a second time, so this is a swap, not a bare retry | With a key: `Your xAI plan doesn't have OAuth API access yet; using your XAI_API_KEY instead.` Without: `Your xAI plan doesn't have OAuth API access yet. Use an API key instead: export XAI_API_KEY=... (console.x.ai), or upgrade your SuperGrok plan.` |
| Inference or refresh 403, **already committed this run** | Keep the token. **Never** switch to a key here, same identity-switch rule as a mid-run 401 | `Your xAI plan doesn't have OAuth API access yet. Use an API key instead: export XAI_API_KEY=... (console.x.ai), or upgrade your SuperGrok plan.` |

**Inference 403 and refresh 403 are the same rule, not two.** An earlier
draft only gated 403 on `refresh_tokens()` raising it — but inference never
calls `refresh_tokens()` (only a 401 does), and the documented real-world
case (Hermes issue #26847) is exactly an inference 403 on an otherwise-valid
token. So the `_committed`-gated 403 rule above applies identically whether
the 403 comes from an inference call or from a refresh call; "The shared
mapper" and "The OAuth runtime" below must not say 403 "propagates
unchanged, no fallback either way" — that was true for genuinely transient
failures, never for 403.
| 402/426 on a well-formed request (right endpoint, full header set), at any time | Until a captured response body proves otherwise, treat as usage-pool exhaustion: log the body via stdlib `logging.getLogger("kadmon.auth.xai").warning(...)` | `You've hit your weekly xAI usage pool. Wait for the reset shown on grok.com, or set XAI_API_KEY to keep going.` |
| 402/426 where the request used `api.x.ai` instead of the proxy, or dropped a required header, at any time | Kadmon bug — `logging.getLogger("kadmon.auth.xai").error(...)`, this is not the user's account | `Something went wrong signing requests to xAI. This is a Kadmon bug, not your account — please file an issue.` |

This is the first use of stdlib `logging` in this codebase (nothing new,
not a framework — just unused so far), and with no handler configured
anywhere, a bare `logging.getLogger(...).warning(...)` call is silently
dropped by Python's default "handler of last resort," which only prints
`WARNING`-and-above to stderr *without* the log record's extra context in
some configurations — good enough for a human watching the terminal, but
worth being deliberate about: call `logging.basicConfig(level=logging.WARNING)`
once, early in `kadmon/cli.py`'s entry point (not inside `auth/xai.py`,
which shouldn't own global logging config), so the body a later session
needs to correct the pool-exhaustion status code (see below) actually
reaches the user's terminal instead of vanishing.

The last two rows of table B are genuinely hard to tell apart from the HTTP
status alone (both are 402/426): the difference is whether *this* request
used the right endpoint and full header set. If it did, assume pool
exhaustion, not a bug — a Kadmon bug should be caught by the tests in
"Testing these from an intuitive standpoint" below before it ships, not
diagnosed live from a user's error message. The pool-exhaustion status code
is not publicly confirmed; log the full response body the first time this is
hit in practice and correct that row with the real code.

### How this copy actually reaches the user

Pinning exact strings in tables A and B doesn't specify a delivery channel,
and this checkout already has one: `kadmon/cli.py`'s `_make_provider()` (used
by `run`, `chat`, and `continue`) already does
`except ConfigError as exc: click.echo(f"Error: {exc}"); raise SystemExit(1)`
around `build_provider(config)` — the same pattern `resolve_key()` already
relies on today for "no API key configured." Every Stop row in tables A and B
reuses this, rather than inventing a new exception type:

- Every Stop row raises `ConfigError(<the exact table copy>)`. Table A's
  "isn't configured" and "dead grant, no key" rows raise it from
  `resolve_credentials()`, at `build_provider` construction time —
  `_make_provider`'s existing catch handles them with **no code change**
  there.
- Table B's Stop rows (mid-run 401 after the retry, 403, 402/426) raise the
  same `ConfigError` from *inside* the agent call, not at construction time
  — and `cli.py`'s `run`, `chat`, and `continue` commands do **not**
  currently catch anything around that call. Named precisely (checked
  against this branch's `cli.py`): `run` and `continue_session` each call
  `agent.run(task)` once; `chat`'s REPL calls `agent.run(task)` for the
  first turn and `agent.continue_with(task)` for every turn after. This
  needs one new catch site per command, identical to `_make_provider`'s:
  wrap those calls in `except ConfigError as exc: click.echo(f"Error:
  {exc}")`, then `raise SystemExit(1)` for `run`/`continue_session`, or break
  out of the REPL loop for `chat`. For `chat`, skip the "Saving session..."
  step that `KeyboardInterrupt` triggers — not because there's nothing to
  save (there may be, from earlier successful turns), but because resuming
  a saved session into the same broken credential on the next `kadmon
  continue` isn't useful; a fresh sign-in should start clean instead. **Do
  not** add this catch inside `AgentLoop` itself — the ReAct loop's own
  error handling is out of scope (see "Out of scope for v1"); the catch
  belongs at the CLI command layer, same altitude as `_make_provider`'s
  existing one.
- Table A's one non-error row — "using your XAI_API_KEY instead" — is not an
  exception, it's an FYI on an otherwise-successful path, so it needs its own
  channel, and it fires from **two different moments** (construction-time
  fallback in `resolve_credentials()`, and the mid-run adapter's own
  start-of-run-equivalent fallback — see "The OAuth runtime"), so it's one
  named helper, not duplicated `click.echo` calls: `emit_auth_notice(text:
  str) -> None` in `kadmon/auth/xai.py`, a thin wrapper around `click.echo`
  that exists so both call sites share one implementation, not two that
  could drift in format. Add `notice: str = ""` to `ResolvedCredentials`.
  `factory.build_provider` sets `provider.notice = creds.notice` as a plain
  attribute on the constructed provider (not part of the `LLMProvider`
  interface — purely a hook for the CLI to read) when non-empty.
  `_make_provider` checks `getattr(provider, "notice", "")` right after
  `build_provider` returns and calls `emit_auth_notice()` with it — the
  construction-time case (this is what covers testing case 5). The adapter
  calls `emit_auth_notice()` directly, once, at the moment its own
  start-of-run fallback happens mid-run (this is what covers testing case
  27/28's key-fallback path — a delivery moment the construction-time-only
  channel couldn't reach, which an earlier pass left unaddressed even after
  adding the fallback logic itself).

### The shared mapper — corrected signature, and who calls it with what

An earlier pass pinned `interpret_http_error(exc: openai.APIStatusError) ->
ConfigError` as *the* single function covering "401 → dead grant vs.
transient vs. 403 vs. 402/426." That signature can't actually do the job:
the start-of-run refresh call talks to `auth.x.ai` over plain
`urllib`/form-POST, not the `openai` SDK, so there is no `APIStatusError` to
hand it there; a 401 is not one meaning (first mid-run 401 is a retry, not
an error at all; a *second* mid-run 401 is table B's stop copy; a
start-of-run 401 with a key available is a notice-and-fallback, not a raise;
only a start-of-run 401 with **no** key is a raise); and "transient failure"
(timeout, 5xx, 429) isn't an HTTP status `openai.APIStatusError` carries
either — those raise as `openai.APITimeoutError` / `APIConnectionError`.
Corrected:

```python
def interpret_http_error(
    status_code: int | None,
    *,
    body: dict | str | None = None,
    request_url: str = "",
    request_headers: dict[str, str] | None = None,
    when: Literal["start", "mid"],
) -> ConfigError:
    """Given a status/context, return the ConfigError to raise. Never called
    for a case that resolves without raising (key fallback, first mid-run
    retry) — those are handled by their callers directly, not through here.
    `status_code` is always set on the returned ConfigError (see below) so a
    caller like init's grok branch can branch on it without parsing copy."""
```

`when="start"` produces the **no-key** table A copy specifically (`"Signed
in xAI session ended. Run kadmon login grok..."`) — the with-key notice
("using your XAI_API_KEY instead") is never something `interpret_http_error`
returns, because that path doesn't raise at all; it's a successful fallback
with `emit_auth_notice()`, handled by the caller directly before
`interpret_http_error` would even be reached.

**Every `ConfigError` this mapper returns carries a `status_code: int | None`
attribute** (e.g. `exc = ConfigError(copy); exc.status_code = status_code;
return exc` — a plain attribute, not a new exception hierarchy). This is
what lets a caller that needs to distinguish 403 from a transient failure
(init's grok branch, below) branch on `exc.status_code == 403` instead of
matching on message text, which an earlier pass left unspecified.

A convenience overload, `interpret_http_error_from(exc: openai.APIStatusError,
when=...)`, reads `exc.status_code`, `exc.body`, `exc.request.url`, and
`exc.request.headers` and calls the primitive version — that's the one the
mid-run adapter and the login-test path (below) actually call; the primitive
version is what handles the start-of-run refresh path, which has no SDK
exception to unpack in the first place.

**The 402/426 well-formed-vs-Kadmon-bug predicate — an earlier draft left
this as "check which base URL/headers the request used" without saying how
to check.** That's not implementable as stated: comparing `request_url`
against the `XAI_OAUTH_BASE_URL` *constant* never matches, because the
constant is `https://cli-chat-proxy.grok.com/v1` while an actual request URL
is something like `https://cli-chat-proxy.grok.com/v1/chat/completions` —
equality against the base fails on every real request, well-formed or not.
And HTTP header names are case-insensitive; the `openai`/`httpx` stack may
send or report them lowercased, so a case-sensitive key comparison against
`XAI_OAUTH_HEADERS` (which is written with mixed case for readability) would
also misclassify a perfectly well-formed request. The actual predicate,
inside `interpret_http_error`/`interpret_http_error_from`, applies **only**
to 402/426 on the inference host (never to 403, and never to a refresh call
to `auth.x.ai` — this predicate has no meaning there):

```python
from urllib.parse import urlparse

def _is_well_formed_xai_request(request_url: str, request_headers: dict[str, str]) -> bool:
    host = urlparse(request_url).hostname or ""
    have = {k.lower() for k in request_headers}
    need = {k.lower() for k in XAI_OAUTH_HEADERS}
    return host == "cli-chat-proxy.grok.com" and need.issubset(have)
```

Well-formed (`host == "cli-chat-proxy.grok.com"` and every required header
name present, case-insensitively) → pool-exhaustion copy. Anything else —
`host == "api.x.ai"`, a different host entirely, or a missing header — →
the Kadmon-bug copy. Compare by *hostname*, never by string equality against
the base URL constant, and compare header *names* case-insensitively, never
exact-case.

**`refresh_tokens()`'s own failure contract, pinned** (an earlier draft left
this implied):

- Success: persist (self-persisting, per "Token storage"), return
  `StoredTokens`. Does **not** call `clear_tokens()` itself in any branch —
  that decision belongs to the caller, because what "dead grant" should
  *do* differs by who's asking.
- HTTP 401 or JSON `invalid_grant` from the refresh call — a genuinely dead
  grant — raises a new, distinct `DeadGrantError` (not `ConfigError`): the
  caller (start-of-run resolution, or the mid-run adapter) decides whether
  that means "clear and fall through to a key" or "clear and stop," which
  differ by *when* it happened, not by what `refresh_tokens()` itself knows.
- HTTP 403, or a timeout/5xx/429, from the refresh call: raises
  `ConfigError` directly, via `interpret_http_error(status_code, when="start",
  ...)` — these never mean "clear the token," in either table, so there's no
  ambiguity for `refresh_tokens()` to defer.

**Call sites, now that the contract is split:**

- `resolve_credentials()`'s grok branch catches `DeadGrantError` from its
  refresh call, calls `clear_tokens()`, then proceeds to step 2 (key
  fallback with `notice` set) or step 3 (`ConfigError` from
  `interpret_http_error(401, when="start")` when no key resolves). A 403 or
  transient `ConfigError` from `refresh_tokens()` propagates straight up
  unchanged — token stays on disk either way.
- `XAIRefreshAdapter` calls `refresh_tokens()` on **every** inference 401,
  whether or not it's already produced output this run (see "The OAuth
  runtime" for the full, now-unified state machine — a plain inference 401
  is never itself treated as a dead grant; only what `refresh_tokens()`
  reports decides that). A `DeadGrantError` there means: clear the token,
  then either fall back to a key (not yet committed) or stop
  (`interpret_http_error(401, when="mid")`, already committed) — never a
  fallback once committed. A 403/transient `ConfigError` from that refresh
  propagates unchanged, no retry, no fallback either way.
- The adapter calls `interpret_http_error_from(exc, when=...)` for
  403/402/426 on the *inference* call itself (not the refresh), and for a
  401 that survives one refresh-and-retry cycle without resolving.
- **The login-test path** (`credentials_override`, in `kadmon login`/`init`,
  which the wrap table already says is never wrapped in the adapter) needs
  its *own* thin catch — not `XAIRefreshAdapter`, since that would refresh
  and persist a token nobody approved yet. This is the gap an earlier pass
  left open: `_test_provider`'s generic `except Exception` swallowed a login
  test's 403/402/426 as an 80-character-truncated SDK message, so table B's
  copy never reached `kadmon login`/`kadmon init` at all. Fix: the code path
  that calls `build_provider(..., credentials_override=creds)` during login
  catches `openai.APIStatusError` directly around that one `complete()` call
  and converts it via `interpret_http_error_from(exc, when="start")` **before**
  it ever reaches `_test_provider`'s generic handler — a thin, refresh-free
  wrapper, not `GrokProvider` owning the mapping (that would put auth logic
  back in the provider) and not the adapter (which would refresh/persist).
- `_test_provider()` (used by `init` and `login`) currently does
  `except Exception as exc: return False, str(exc).split("\n")[0][:80]` —
  fine for a raw SDK message, but it would mangle table B's longer,
  deliberately-worded copy. Special-case it: a caught `ConfigError` (from
  the login-test wrapper above, or from `resolve_credentials()`) returns
  `False, str(exc)` untruncated; anything else keeps the existing
  80-character first-line truncation.

### Testing these from an intuitive standpoint

Unit tests should mock both `auth.x.ai` (device/token/refresh) and
`cli-chat-proxy.grok.com` (inference) — per AGENTS.md, never hit either in
CI — but the cases to cover are the ones above, picked by what a real person
will actually hit, not just the happy path:

1. Fresh sign-in, approve promptly → stored token, `kadmon run` works.
2. Fresh sign-in, let the device code expire → "Code expired" message, no stack trace.
3. Fresh sign-in, deny the login in the browser/device page → "Sign-in was
   denied" message, distinct from the expiry message in case 2.
4. Stored token, access token expired, refresh succeeds (with a *new*
   `refresh_token` in the response) → transparent, user sees nothing, and the
   new refresh token is the one persisted (see "Token storage" write-back rule).
5. **Start-of-run** (table A): stored token, refresh revoked
   (401/`invalid_grant`) before `build_provider` makes any request this run,
   `XAI_API_KEY` **is** set → the "using your XAI_API_KEY instead" notice,
   request still succeeds, old token cleared.
6. **Start-of-run** (table A): same as case 5, no key set → the "sign in
   again" message, old token cleared, command stops before any request.
7. No `[xai]` entry, no key resolves → the "isn't configured" first-run
   message, not a generic error.
8. Valid token, account not entitled (403) → the not-entitled message (not
   the "using your key" copy from case 5 — this token is still valid, just
   ungranted), token is **not** cleared (retryable after a plan upgrade
   without a fresh login).
9. **Mid-run** (table B): the retry adapter's refresh+retry succeeds on the
   first 401 → transparent, no user-visible message; assert this happens on
   **both** `complete()` and `stream()`, and that the SDK's 401 is caught as
   an *exception* (`openai.AuthenticationError` / `APIStatusError` with
   `status_code == 401`), not read off a return value.
10. **Mid-run** (table B), the critical case tables A and B used to
    contradict: retry adapter's refresh+retry fails a *second* time, with
    `XAI_API_KEY` **set** → stops with the mid-run "session ended" message;
    must **not** print or behave like case 5's "using your key instead" —
    assert no fallback request is made on the key.
11. 402/426 on a well-formed proxy request → pool-exhaustion message, response
    body logged, request not retried as if it were a bug.
12. 402/426 where the request used the wrong endpoint or dropped a header (a
    Kadmon bug scenario, simulated in the test, not a live account) → the
    Kadmon-bug message, distinct from case 11's copy.
13. `kadmon init` with both an OAuth session and `XAI_API_KEY` present → OAuth
    wins, and the `[✓]` marker in the provider list says *why* (e.g. `[✓]
    signed in as you@x.ai` vs. `[✓] API key`), not just that it's ready.
14. `kadmon logout grok` then `kadmon run` → falls back to `XAI_API_KEY` if
    set, otherwise the same "not signed in" prompt as a first run.
15. `kadmon login grok` with no prior `kadmon init` at all → creates the grok
    provider entry itself (see "Standalone login" below); `kadmon run`
    afterward works with no extra flags when grok is the only provider.
16. Any non-grok provider (Anthropic/OpenAI/Gemini) resolves its credentials
    normally after a grok OAuth session exists — assert it never reads
    `tokens.toml` or receives `XAI_OAUTH_BASE_URL`/`XAI_OAUTH_HEADERS`. This
    is the "auth precedence must be grok-gated" requirement below; test it
    directly, don't just trust the gate.
17. **Start-of-run, transient failure**: stored token, the refresh call times
    out (or returns 500/429) rather than 401/`invalid_grant`, `XAI_API_KEY`
    **is** set → the token is **not** cleared, no fallback request is made on
    the key, and the user sees the "couldn't reach xAI" message, not the
    "using your key instead" notice. This is the case that distinguishes a
    dead grant from a network blip.
18. `_make_provider`'s existing `except ConfigError` catch handles table A's
    Stop rows with no code change to that function — assert a `ConfigError`
    raised from `resolve_credentials()` produces exactly `Error: <table
    copy>` and `SystemExit(1)`, the same as today's "no API key configured"
    case.
19. A `ConfigError` raised *mid-run* (simulate table B's 403 or the
    second-401 case during `agent.run(task)`) is caught by `run`/`continue`'s
    new catch site and by `chat`'s per-turn catch — not left to propagate as
    a traceback, and not caught inside `AgentLoop` itself.
20. The "using your key instead" notice has **two** valid delivery sites,
    not one — split so this case doesn't fight case 27: (a) construction-time
    fallback (case 5) is echoed exactly once via `provider.notice`, read by
    `_make_provider` — not printed from inside `resolve_credentials()` or
    `build_provider` directly; (b) the adapter's own mid-run fallback (case
    27/28) calls `emit_auth_notice()` directly, not through
    `provider.notice`/`_make_provider`, since `_make_provider` has already
    returned by the time that fallback happens. Assert each fires from its
    own site and neither repeats on a second command/call in the same
    process.
21. Two worker threads (`WorkerPool`, sharing one `GrokProvider`-backed
    adapter) both hit a 401 at the same time → `refresh_tokens()` runs
    exactly once; the thread that loses the race reuses the token the winner
    already installed instead of refreshing again.
22. The API-key path (including table A's start-of-run fallback to
    `XAI_API_KEY`) is **not** wrapped in the mid-run retry adapter — only a
    live OAuth `ResolvedCredentials` (the one with `XAI_OAUTH_BASE_URL`) is.
    Assert directly, not just by absence of a failure.
23. `_test_provider`'s failure copy is untruncated when the underlying
    exception is a `ConfigError` (asserts the table B not-entitled message,
    which is longer than 80 characters, survives intact) and still truncated
    to 80 characters for a raw, non-`ConfigError` SDK exception.
24. Login writes `tokens.toml` at mode `0600`. A repeat `kadmon login grok`
    while already signed in overwrites the existing entry with no special
    handling — same code path as a fresh login. `kadmon logout grok` with no
    `[xai]` entry present is a no-op, not an error.
25. After a mid-run refresh (case 9), `email` on the stored token entry is
    unchanged from before the refresh — refreshing must not blank the cached
    address the init `[✓]` marker displays.
26. A live OAuth inference request actually carries `XAI_OAUTH_BASE_URL` and
    the full `XAI_OAUTH_HEADERS` set — assert this directly against the
    constructed client/request, not just that the happy path returns a
    response.
27. **The gap between the 60-second margin and a real revocation:** stored
    token whose access token is *not* near expiry (so the construction-time
    refresh check in auth precedence step 1 doesn't even run), but the grant
    was revoked server-side — the *first* `complete()`/`stream()` call this
    run gets a 401 with `_committed` still `False`. Assert the adapter calls
    `refresh_tokens()` (not an immediate `clear_tokens()` off the raw
    inference 401 — that's exactly the bug this case exists to catch) and
    that call raises `DeadGrantError`. With `XAI_API_KEY` set → the same
    "using your key instead" notice (via `emit_auth_notice()`, not
    `_make_provider`, since this fires mid-run) and fallback as case 5, not
    the mid-run stop message. Without a key → the "sign in again" copy
    (`when="start"`), not the mid-run "partway through this run" copy — this
    is the case earlier passes left uncovered entirely.
28. Same setup as case 27, but the first call *succeeds* before a later call
    401s → `_committed` is now `True`, so that later 401 is genuinely
    mid-run: retry once, then table B's stop copy if it 401s again — no key
    fallback, unlike case 27.
29a. `stream()`'s first call yields one chunk, then 401s partway through the
    same call (HTTP body still open), and `refresh_tokens()` **succeeds**
    (the grant was fine, only the access token needed rotating) → no retry
    of this call (`already_yielded` is `True`), but this is **not** the
    "session ended" copy — assert the distinct `StreamInterruptedError`
    ("Connection interrupted... your session is fine") is what surfaces,
    the token is kept, and a *following* call in the same run succeeds
    transparently against the freshly rotated token.
29b. Same setup as 29a, but `refresh_tokens()` raises `DeadGrantError`
    instead → this genuinely is table B's "session ended partway through
    this run" stop copy, no key fallback — `_committed` is `True` here (a
    chunk was already yielded), consistent with case 28's rule, not 29a's.
    Assert 29a and 29b produce different copy for the same "401 after a
    yielded chunk" trigger, distinguished only by what `refresh_tokens()`
    reports.
30. `refresh_tokens()` succeeds (token merely needed a refresh, grant not
    actually dead) but the retried call 401s again anyway, on a call where
    `already_yielded` was `False` → stop (`interpret_http_error`, `when`
    matching `_committed`), no further retries, no key fallback either way
    — distinct from cases 27/28/29, which
    are about `DeadGrantError`, not a healthy refresh followed by a second
    failure.
31. `kadmon init`'s provider list `[✓]` marker never makes a network call —
    assert no request to `auth.x.ai` or the inference host happens just from
    listing providers, even with a stored token present.
32. `kadmon init`'s grok branch, selected explicitly: a live token → "already
    signed in" copy, no sign-in or paste-key prompt, and a key pasted anyway
    (if forced past that message) is never actually reachable. A dead token
    (`DeadGrantError` on the validation call) → sign-in offered, and a
    pasted key **is** reachable afterward (the dead entry gets cleared). A
    transient failure on that same validation call → the "couldn't reach
    xAI" copy, **neither** sign-in nor paste-key offered this run, and the
    stored token is untouched.
33. Login-test 403 (`kadmon login grok` against an account not entitled to
    OAuth API access) surfaces the not-entitled copy through
    `_test_provider`, untruncated — not an 80-character-truncated raw SDK
    message, and not silently treated as a generic connection failure.
34. The 402/426 well-formed-vs-Kadmon-bug predicate (see "The shared mapper"
    402/426 predicate) is tested directly against realistic request shapes:
    a request to `https://cli-chat-proxy.grok.com/v1/chat/completions` with
    all of `XAI_OAUTH_HEADERS` present (case-insensitively) classifies as
    pool-exhaustion; a request to `https://api.x.ai/v1/...`, or one missing
    any required header, classifies as a Kadmon bug — assert both directions,
    not just the happy one, and assert header-name comparison is
    case-insensitive (the `openai`/`httpx` stack may lowercase header names).

Case 13 in particular is a legibility problem, not just a logic problem: two
different "already good to go" states should not render identically in the
init list, or the user can't tell which one they're on.

## Shape in this codebase

**Prerequisite: `feat/multi-provider` (branch + PR #2).** Everything below
extends that branch's code, not `main`. Checked directly (2026-08-19): `main`
has none of `ProviderConfig`, `resolve_key()`, `factory.py`, `credentials.toml`,
or `kadmon/providers/grok.py` — provider construction on `main` is a single
`_make_provider()` in `cli.py` reading env vars into a flat `Settings` model.
If PR #2 has not landed by the time this is implemented, rewrite this section
against whatever `cli.py` looks like then; do not invent a parallel auth
system alongside the old one.

On `feat/multi-provider`, confirmed by reading the actual files:

- `kadmon/config.py` — `ProviderConfig.auth: str`, `resolve_key() -> str`,
  `KIND_GROK`, `CREDENTIALS_PATH = ~/.config/kadmon/credentials.toml`
- `kadmon/providers/factory.py` — `build_provider(config, max_tokens)` is the
  only place that constructs a provider class (an AST test in
  `tests/test_provider_wiring.py` enforces this)
- `kadmon/providers/grok.py` — `GrokProvider(OpenAIProvider)`, pins
  `XAI_BASE_URL = "https://api.x.ai/v1"`, already takes `base_url: str = ""`
- `kadmon/providers/openai_provider.py` — wraps `openai.OpenAI(api_key=,
  base_url=)`; has no `headers` parameter yet, needs one

### The credential contract — one type, not two

Earlier drafts of this doc specified `resolve_key()` returning a bearer string
two different ways in two different sections. That is gone. There is exactly
one contract:

```python
@dataclass
class ResolvedCredentials:
    token: str
    base_url: str = ""                          # "" = provider's own default
    headers: dict[str, str] = field(default_factory=dict)
    notice: str = ""                             # see "How this copy actually
                                                  # reaches the user" above —
                                                  # a one-time FYI, not an error
```

- `env:` / `credentials:` sources (today's behavior) return
  `ResolvedCredentials(token=key)` — empty `base_url`, empty `headers`, empty
  `notice`.
- `oauth:xai`, once a token is resolved and refreshed, returns
  `ResolvedCredentials(token=access_token, base_url=XAI_OAUTH_BASE_URL,
  headers=XAI_OAUTH_HEADERS)` (constants below) — `notice` empty on the
  normal path.
- Table A's start-of-run fallback (dead grant, `XAI_API_KEY` set) returns
  `ResolvedCredentials(token=key, notice="Signed-in xAI session ended; using
  your XAI_API_KEY instead.")` — a plain API-key credential plus the
  one-time FYI, not an error.

`ProviderConfig.resolve_key()` is renamed `resolve_credentials()` and returns
this type everywhere, not a bare string. `factory.build_provider` gains an
optional `credentials_override: ResolvedCredentials | None = None` parameter
— when given, it's used instead of calling `config.resolve_credentials()`.
This is what lets `kadmon login` test a token before it's ever written to
`tokens.toml` (see "Standalone login" below) without constructing
`GrokProvider` directly, which the Constraints section forbids.

```python
creds = credentials_override or config.resolve_credentials()
GrokProvider(
    model=config.model,
    api_key=creds.token,
    base_url=creds.base_url or config.base_url,
    headers=creds.headers,
    max_tokens=max_tokens,
)
```

`GrokProvider.__init__` gains `headers: dict[str, str] | None = None` and
forwards it to `OpenAIProvider`, which passes `default_headers=headers or
None` into `openai.OpenAI(...)`. The `openai` SDK lets `default_headers`
override its own defaults, including `User-Agent` — so the pinned
`User-Agent: xai-grok-cli` and `x-grok-*` headers below take effect as sent.

**Do not pin `Accept`.** The SDK sets `application/json` for `complete()` and
negotiates SSE for `stream()` on its own; forcing a static `Accept` risks
breaking whichever call path xAI's proxy doesn't expect. Only add it later if
a captured `grok-build` trace proves it's required on both paths, and cite
that trace in the PR.

### Wire constants — pinned here, not linked

Prior art is provenance for *why* these are right; this table is the spec a
writer implements against, so it does not depend on a third-party doc staying
up:

| Constant | Value |
| --- | --- |
| Issuer | `https://auth.x.ai` |
| Authorization endpoint | `https://auth.x.ai/oauth2/authorize` |
| Device authorization endpoint | `https://auth.x.ai/oauth2/device/code` |
| Token endpoint | `https://auth.x.ai/oauth2/token` |
| Userinfo endpoint | `https://auth.x.ai/oauth2/userinfo` |
| `client_id` | `b1a00492-073a-47ea-816f-4c329264a828` |
| Scope (v1) | `openid profile email offline_access grok-cli:access api:access` |
| Device-code grant | `urn:ietf:params:oauth:grant-type:device_code` |
| `XAI_OAUTH_BASE_URL` (inference) | `https://cli-chat-proxy.grok.com/v1` |

`XAI_OAUTH_HEADERS`, in addition to `Authorization: Bearer <token>` (which
`openai.OpenAI(api_key=...)` already sets):

```
x-xai-token-auth: xai-grok-cli
x-grok-client-identifier: grok-shell
x-grok-client-version: 0.2.93   # pinned v1 value, verified against grok-build
                                 # in the gents spike. Bumping this to track a
                                 # newer grok-build release is a follow-up
                                 # task, not a blocker for v1 — ship this value.
User-Agent: xai-grok-cli
```

The URLs and constants above are only half the wire contract — the actual
HTTP requests need pinning too, or a writer who sends JSON instead of form
data (or omits `client_id` on poll/refresh) ships a login that silently never
completes. The first three requests below share one shape: `POST`,
`Content-Type: application/x-www-form-urlencoded`, `Accept: application/json`.
The fourth — userinfo — is different and called out separately in its own row.

| Request | Endpoint | Method / fields |
| --- | --- | --- |
| Device code | Device authorization endpoint | `POST` form: `client_id`, `scope` |
| Poll for token | Token endpoint | `POST` form: `grant_type=urn:ietf:params:oauth:grant-type:device_code`, `client_id`, `device_code` |
| Refresh | Token endpoint | `POST` form: `grant_type=refresh_token`, `client_id`, `refresh_token` |
| Userinfo (email fallback, only if `id_token` absent) | Userinfo endpoint | `GET`, `Authorization: Bearer <access_token>` header, no body |

The `email` claim (from `id_token` or this userinfo call) is the JSON key
`email` — not `preferred_username` or any other OIDC claim some providers use
instead.

None of these send a client secret (public client, per open question 1).
**Wait** the device-code response's `interval` field before the *first* poll,
not just between subsequent ones (RFC 8628 default: 5 seconds if the field is
absent) — polling immediately and then waiting is the wrong order and xAI may
rate-limit an immediate poll.

Device-code poll loop (RFC 8628, xAI's actual behavior per the endpoints
above) — see tables A and B under "Error states" for the authoritative action
per signal (the earlier single-table version this paragraph originally
pointed to has been split). The HTTP envelope matters and is easy to get
wrong: the token endpoint answers **HTTP 200** with an `access_token` body on
success, and **HTTP 400 or 401 with a JSON `error` field** — not a generic
failure — while pending or on a recoverable condition. Parse the JSON body's
`error` key (`authorization_pending`, `slow_down`, `expired_token`,
`access_denied`) before deciding the request failed. A writer who treats any
non-200 as "login failed" will never complete a login, because
`authorization_pending` arrives as an HTTP 400.

v1 ships **device-code only** — no browser/PKCE flow in this pass (see open
question 2). `verification_uri` and `user_code` in the Target UX examples
above are **values from the device-code response, not hardcoded strings** —
don't bake `https://accounts.x.ai/device` into the code; print whatever the
response actually returns.

### Token storage — file only, decided

Keychain is **out of v1.** Do not add a `keyring` dependency — it was listed
as a maybe in an earlier draft; this drops it. Store:

```
~/.config/kadmon/tokens.toml, mode 0600

[xai]
access_token = "..."
refresh_token = "..."
expires_at = 1234567890   # unix seconds; see below for how this is computed
email = "you@x.ai"        # decoded from id_token if present, else one
                           # userinfo call at login time; cached, not
                           # re-fetched on every run
```

**`expires_at` comes from the token response's `expires_in` field:**
`expires_at = now + expires_in`, computed at the moment the token/refresh
call returns. Do **not** parse a JWT `exp` claim as the source — access
tokens are not guaranteed to be JWTs, and a writer who requires that shape
cannot implement this against an opaque token. **If `expires_in` is absent
from the response** (RFC 6749 marks it RECOMMENDED, not required — a literal
`expires_at = now + expires_in` would crash on `None`), fall back to 900
seconds (15 minutes — the lifetime the gents spike observed access tokens
actually using) and treat the token as needing the 60-second-margin refresh
check the same as any other. Decoding an `id_token`'s claims (for the cached
email) is separate and only relevant if an `id_token` is present — do that
with stdlib `base64` + `json` (split on `.`, base64url-decode the payload
segment, `json.loads`); no PyJWT or other JWT dependency.

`StoredTokens` is a plain dataclass, not just a type name used informally:

```python
@dataclass
class StoredTokens:
    access_token: str
    refresh_token: str
    expires_at: int
    email: str = ""
```

**Refresh write-back is not optional and not the caller's job to remember.**
`refresh_tokens()` (see "The OAuth runtime" below) persists the result
itself — via `save_tokens()` — before returning, on **every** successful
refresh, not just the ones the mid-run adapter triggers. This closes a gap
from an earlier draft, which left "refresh, then caller persists" as an
implied step that the auth-precedence's 60-second-margin refresh (a
different call site than the mid-run adapter) never actually named. One
function, one persist, every caller gets it automatically:

- `access_token` and the recomputed `expires_at` (`now + expires_in`) are
  always overwritten.
- `refresh_token` is overwritten **only if the response included a new
  one** — per RFC 6749 the token endpoint may rotate it on every use; if
  Kadmon keeps serving the old one, the next refresh fails and the session
  dies for no visible reason. If the response omits `refresh_token`, keep
  the one already on disk.
- `email` and any other cached, non-token field carry over unchanged — a
  token refresh response has no reason to touch them, and building a new
  `StoredTokens` that silently drops `email` would blank the init `[✓]`
  marker's "signed in as ..." copy for no reason tied to the refresh itself.

**Refresh early, not exactly at expiry:** treat a token as needing refresh
when `now >= expires_at - 60` (a 60-second margin), so the first request of
a `kadmon run` isn't the one that discovers the token just expired.

Tokens are global (`GLOBAL_CONFIG_DIR`), not per-repo — same as
`credentials.toml` today.

### The OAuth runtime — named module, not implied by the config layer

This needs its own module, not a few hundred lines inside `config.py`:
`kadmon/auth/xai.py` (not under `providers/` — it's not a provider, and
`GrokProvider` staying a stateless `OpenAIProvider` subclass depends on this
living elsewhere). Public functions:

- `device_login() -> StoredTokens` — runs the full device-code flow
  (request code, print `verification_uri`/`user_code` from the response,
  poll per the envelope rules above), returns the tokens **without** writing
  anything to disk. Deliberately: the standalone-login path below calls this
  before it's allowed to persist anything.
- `load_tokens() -> StoredTokens | None` — reads `tokens.toml`.
- `refresh_tokens(tokens: StoredTokens) -> StoredTokens` — calls the token
  endpoint with `grant_type=refresh_token`, **persists the result itself**
  on success (see "Token storage" write-back rule — this is not the caller's
  job); on failure, raises `DeadGrantError` (401/`invalid_grant`) or
  `ConfigError` (403, timeout, 5xx, 429) per "The shared mapper" above — it
  never calls `clear_tokens()` itself in any branch, that's the caller's call.
- `save_tokens(tokens: StoredTokens) -> None`, `clear_tokens() -> None`.

**Which paths get wrapped is its own decision, pinned here first:**

| Path | Wrapped in the adapter? |
| --- | --- |
| Live OAuth (`resolve_credentials()` returned `base_url=XAI_OAUTH_BASE_URL`) | **Yes** |
| API-key path — any kind, including grok's start-of-run fallback to `XAI_API_KEY` (table A) | No |
| `credentials_override` (login/init test — see "Standalone login") | No |

Only a genuinely live OAuth session gets the adapter. Wrapping the API-key
path too would mean an API-key 401 triggers `refresh_tokens()` against a
`tokens.toml` entry that's already been cleared (table A's fallback already
ran), producing the mid-run "session ended" copy for a plain bad-key error.
Wrapping the login-test path would mean a failed login test tries to refresh
and persist tokens nobody has approved saving yet.

The adapter has a name — `XAIRefreshAdapter`, defined in `factory.py`
alongside `build_provider` (not in `kadmon/auth/xai.py` — see "Rebuild
location" below) — and holds one mutable reference to the current inner
`GrokProvider`, swapped in place on a successful refresh so callers holding
the adapter don't need to know a rebuild happened.

**Two questions, not one — the previous pass's "one flag" collapse conflated
them.** Pass 7 tried to reduce this to a single `_committed` boolean gating
everything. That's wrong in one specific way: whether *this call* can be
safely retried and whether the run can still switch credentials are
independent questions, and a single flag can't answer both — a `stream()`
401 arriving after a chunk has already reached the display must never
retry (that's `_committed`'s job), but a *second, later* `complete()` call
in an otherwise-healthy run 401ing absolutely can retry (refresh and try
again) even though `_committed` is `True` by then — it just can't fall back
to a key if the retry fails. Splitting them:

- **`_committed: bool`** — has this adapter ever *delivered* output before
  this incident (any earlier call succeeded, or a call before this one
  already yielded a chunk)? Starts `False`, flips to `True` the first time
  either happens, stays `True` for the rest of the run. This gates **key
  fallback only** — once `True`, a dead grant always means stop, never
  switch credentials.
- **`already_yielded` (call-scoped, not stored on the adapter)** — has *this
  specific* `complete()`/`stream()` call already handed output to the
  caller before the 401 arrived? Always `False` for `complete()` (it never
  partially returns before erroring). For `stream()`, `False` until the
  first chunk of *this* call is yielded, then `True` for the rest of this
  call only — the next call starts over at `False`. This gates **whether
  this call can be retried**, independent of `_committed`.

**On any inference 401, always:** call `refresh_tokens()` (locked — see
concurrency below), regardless of `_committed` or `already_yielded`. There
is no branch where a raw inference 401 is treated as a dead grant directly
— "dead grant" means only what `refresh_tokens()` itself reports, the same
definition table A's construction-time check uses.

- `refresh_tokens()` succeeds (the grant is fine, the access token just
  needed rotating) → rebuild the inner `GrokProvider` in `factory.py` with
  the new access token, **`base_url=XAI_OAUTH_BASE_URL`, and
  `XAI_OAUTH_HEADERS`** (not just the token — see "Rebuild location"),
  copying `model`/`max_tokens` from the provider being replaced.
  - If `already_yielded` is `False` (always true for `complete()`; true for
    `stream()` only before its first chunk): retry the same call once on the
    rebuilt provider. That retry succeeding is the normal, silent path — the
    common case, not an error. If the retry *also* 401s, stop:
    `interpret_http_error(401, when="mid" if _committed else "start")`, no
    further retries, no key fallback either way — a token that survives a
    genuine refresh but still 401s on inference isn't a credentials problem
    this spec's fallback logic can paper over.
  - If `already_yielded` is `True` (a `stream()` 401 arriving after this
    call already sent output to the display): **do not retry** — deduping
    partially-streamed output is out of scope (Constraints: no
    streaming-contract changes). The refresh above still happened and
    still installed a good token for the *next* call, so don't tell the
    user their session ended (it didn't). **Delivery, checked against
    `AgentLoop._call_llm`:** that loop does
    `for chunk in self.provider.stream(...): ...; if chunk.event == DONE:
    response = chunk.response` and then calls `_process_response(response)`
    unconditionally — stopping the generator with no `DONE` leaves
    `response = None` and crashes on `response.tool_calls`; synthesizing a
    fake `DONE` would be a streaming-contract change (Constraints forbid
    it). So this raises a **new, distinct exception**, `StreamInterruptedError`
    (a `ConfigError` subclass, so every existing `except ConfigError` catch
    still handles it as a fallback) with the "Connection interrupted..."
    copy. `run` and `continue_session` treat it like any other `ConfigError`
    — print and exit, acceptable since they're one-shot commands. `chat`'s
    REPL catch is the one place that matters: catch
    `StreamInterruptedError` *before* the general `ConfigError` case, print
    the line, and **stay in the REPL** (don't break, don't skip the
    "Saving session..." step) — unlike a real auth failure, this one is
    recoverable by just sending the next message.
- `refresh_tokens()` raises `DeadGrantError` → `clear_tokens()`.
  - `_committed` is `True` → stop: `interpret_http_error(401, when="mid")`,
    never a key fallback, regardless of `already_yielded` — once the run has
    delivered output under one identity, it doesn't switch, whether or not
    this particular call could otherwise be retried.
  - `_committed` is `False` (note: this implies `already_yielded` is also
    `False`, since yielding a chunk would have already set `_committed`) —
    table A's dead-grant row, just discovered via an inference call instead
    of the construction-time check: the grok-only key lookup (see "Auth
    precedence") finds a key → swap the adapter's delegate to a plain,
    unwrapped `GrokProvider` built from that key, empty `base_url`, empty
    `headers` (the mirror image of the OAuth rebuild above), call
    `emit_auth_notice()` once, retry the same call on the new delegate. No
    key → stop: `interpret_http_error(401, when="start")`.
- `refresh_tokens()` raises `ConfigError` with `status_code == 403` → keep
  the token (never `clear_tokens()` — it may become entitled later without
  a fresh login). This is `_committed`-gated the same way `DeadGrantError`
  is, not lumped with transient failures: not yet committed → the
  grok-only key lookup finds a key → fall through to it via
  `emit_auth_notice()` (a distinct not-entitled notice, not the dead-grant
  one); no key → stop with the no-key not-entitled copy. Already committed
  → always stop with the not-entitled copy, never switch credentials.
- `refresh_tokens()` raises `ConfigError` with any other status (timeout,
  5xx, 429 — no `status_code`, or one that isn't 403) → keep the token,
  propagate unchanged, no retry, no key fallback, regardless of `_committed`
  or `already_yielded`. Only these are genuinely "we don't know, stay put" —
  403 is a known, stable answer (not entitled), not an unknown one.

**Once the delegate has been swapped to a plain key-based provider (the
`DeadGrantError`-with-key branch above), the adapter becomes an inert
pass-through for the rest of this process** — callers keep holding the same
`XAIRefreshAdapter` object, but it just forwards `complete()`/`stream()`
straight to the plain delegate with no more refresh logic, no more 401
mapping, no second fallback attempt. `refresh_tokens()` is never called
again on this adapter instance. A subsequent bad-key error from that plain
provider behaves exactly like any other unwrapped API-key path today (an
earlier pass's wrap table already says the API-key path isn't wrapped —
this is that same path, just reached via a mid-run swap instead of
construction-time).

**402/426, any time, regardless of `_committed`/`already_yielded`** (403 is
handled above, `_committed`-gated with a key-fallback branch — 402/426 never
fall through to a key, only 403 and 401 do): route through
`interpret_http_error_from(exc, when="mid" if _committed else "start")` —
one mapping, the same one "The shared mapper" and the login-test path use,
not a second implementation.

**Detection is an exception, not a return value.** `complete()`'s
`_call_with_retry` calls `self.client.chat.completions.create(**kwargs)`
directly and only catches `openai.RateLimitError`, `openai.APIConnectionError`,
`openai.InternalServerError` — a 401 raises `openai.AuthenticationError` (a
subclass of `openai.APIStatusError` with `status_code == 401`) straight
through, uncaught, today. `stream()` calls
`self.client.chat.completions.create(**kwargs)` even more directly (no
`_call_with_retry` at all) and raises the same way, but only once the caller
starts iterating the returned generator. **The adapter's `stream()` cannot
be a bare `yield from inner.stream(...)`** — it needs to know the moment the
first chunk arrives, to flip `_committed` and set `already_yielded` before
handing that chunk onward. So it iterates explicitly:

```python
def stream(self, *args, **kwargs):
    already_yielded = False
    try:
        for chunk in self._inner.stream(*args, **kwargs):
            already_yielded = True
            self._committed = True
            yield chunk
    except openai.AuthenticationError:
        ...  # the 401 handling above, using already_yielded and self._committed
```

**Rebuild location.** The AST guard in `tests/test_provider_wiring.py` only
permits `GrokProvider(...)` construction inside `factory.py` — so every
rebuild above happens there, alongside `build_provider`, never in
`kadmon/auth/xai.py` and never by re-entering `build_provider` (which would
nest another adapter around the new provider instead of just swapping the
token).

**Serialize only the refresh, never the retried call, and only within one
process.** `kadmon/workers.py`'s `WorkerPool` hands the *same*
`XAIRefreshAdapter` to several `AgentLoop`s running in parallel threads. Two
worker threads hitting a 401 at once must not both call `refresh_tokens()`
— the second refresh would either race the first or get told the refresh
token it's holding was already rotated out from under it. The adapter holds
one `threading.Lock`, scoped to exactly this: remember the access token this
call started with; on a 401, acquire the lock; if `load_tokens()` shows a
*different* access token than the one this call started with, another
thread already refreshed — just rebuild this thread's local `GrokProvider`
reference from that fresh token and release; otherwise call
`refresh_tokens()` and rebuild. **Release the lock before making the
retried `complete()`/`stream()` call** — the lock guards the
check-refresh-rebuild sequence only, not the LLM round-trip, or every
parallel worker would serialize on inference latency instead of on the
brief refresh. This is in-process only: two separate `kadmon` processes
signed in to the same account can still race a refresh-token rotation
against each other. That's a known v1 limit (multiple concurrent CLI
processes sharing one xAI session is an edge case, not the target use), not
something this pass tries to solve with cross-process locking.
`WorkerPool.dispatch()` already wraps each `future.result()` (the result of
a worker's `agent.run()`, including any `ConfigError` this mechanism raises)
in `except Exception as e: WorkerResult(..., output=f"Worker error: {e}",
success=False)`, rather than propagating — accepted for v1: a dead OAuth
session kills that one worker's subtask with its message preserved in
`WorkerResult.output`, not the whole `dispatch()` call. Changing that would
be a `WorkerPool` semantics change unrelated to OAuth, out of scope here.

**Why the delegate needs a key resolver, not just a key.** The adapter's
key-fallback branch above needs to call the grok-only key lookup itself
(see "Auth precedence" — `XAI_API_KEY` env var, then the `grok` entry in
`credentials.toml`, never `config.auth`), which means it needs that lookup
function captured at wrap time — `factory.build_provider` passes it in when
constructing the adapter, alongside the initial `GrokProvider`.

The `credentials_override` login-test path (see "Standalone login") is
**not** wrapped in this adapter at all, per the wrap table — login is
testing a token that may never be persisted, and this mechanism's
refresh-and-persist-on-401 must not run against one `save_tokens()` hasn't
been told to keep yet. Its 403/402/426 handling is the separate thin wrapper
described in "The shared mapper" above.

The adapter implements both `complete()` and `stream()` — `kadmon/agent/loop.py`
gates streaming on `hasattr(self.provider, "stream")`, so an adapter missing
`stream()` would silently downgrade every OAuth Grok run to non-streaming,
which is a UX regression, not a safe fallback.

### Auth precedence — the algorithm, not a description, and only for `kind == "grok"`

**This algorithm applies only when `config.kind == KIND_GROK`.** An earlier
draft said `resolve_key()` is "renamed `resolve_credentials()` and returns
this type everywhere," which read as every kind gaining token-file lookup.
It must not: `resolve_credentials()` for Anthropic, OpenAI, and Gemini stays
exactly today's `env:`/`credentials:` logic, full stop — it never reads
`tokens.toml`, never returns `XAI_OAUTH_BASE_URL`, never returns
`XAI_OAUTH_HEADERS`. Only the `KIND_GROK` branch of `resolve_credentials()`
runs the steps below; every other kind is unchanged from before this design
existed. (Test case 16 above exists specifically to catch a writer who
implements this as a blanket change instead of a grok-only branch.)

For `kind == "grok"`, resolved at use time, not cached at load:

1. If `tokens.toml` has an `[xai]` entry: try it, refreshing the access token
   first if it's within the 60-second margin of expiry (this refresh, like
   every refresh, persists itself on success — see "Token storage").
   Refresh succeeds, or no refresh was needed → **OAuth path**, done.
   `refresh_tokens()` raises `DeadGrantError` → clear the `[xai]` entry (via
   `clear_tokens()`) and fall through to step 2 — this is table A's "session
   ended" row, not silent. It raises `ConfigError` with `status_code == 403`
   → keep the token (never clear it), and fall through to step 2 anyway if
   the grok-only key lookup finds a key (with the not-entitled notice, not
   the dead-grant one) — this is not committed yet, so the same
   `_committed`-gated 403 rule from "Error states"/"The OAuth runtime"
   applies at construction time too, not just mid-run. It raises `ConfigError`
   with any other status (timeout, 5xx, 429 — genuinely unknown, not a
   stable "not entitled" answer) → keep the token, propagate unchanged, do
   **not** fall through to step 2.
2. Else if the **grok-only key lookup** finds a key → **API-key path**.
3. Else → **not signed in**; the "isn't configured" row in table A.

**The grok-only key lookup, pinned — an earlier draft said step 2 was
"`env:`/`credentials:`, unchanged from today," which is wrong for grok
specifically.** Today's key lookup for every other kind reads `config.auth`
(`"env:VAR"` or `"credentials:name"`). For grok, `auth` becomes `"oauth:xai"`
the moment a login ever succeeds, and nothing rewrites it back afterward
(dead-grant paths clear the token but don't touch `auth`; only `logout`
does) — so reusing `config.auth` here would try to resolve `"oauth:xai"` as
if it were an `env:`/`credentials:` spec and never find `XAI_API_KEY` or a
`credentials.toml` entry at all. Step 2, and the adapter's key-fallback
branch, and the `[✓] API key` list marker, all use one direct lookup instead,
ignoring `auth` entirely:

```python
def grok_fallback_key() -> str | None:
    return os.environ.get("XAI_API_KEY") or _read_credential("grok") or None
```

Returns `None`, not `""`, when nothing resolves (`os.environ.get` and
`_read_credential` can each hand back an empty string) — every caller treats
`None` as "no key," never a falsy-but-present empty string.

This is a deliberate v1 simplification specific to grok: unlike every other
provider kind, a grok entry's key path only ever checks `XAI_API_KEY` or the
`grok` entry in `credentials.toml` — not an arbitrary `credentials:othername`
`auth` string — because once OAuth has ever been used, `auth` can no longer
be trusted to say what the key path should be.

A live, refreshable token always wins when present. **This is only half of
where a dead grant gets discovered, though:** the 60-second margin above only
refreshes (and so only detects a dead grant) when the stored access token is
already close to its *own* expiry. An access token typically lasts ~900
seconds, so a grant revoked at the source any time before that window is
invisible to this step — the first inference call of the run is what
actually surfaces it, as a plain 401. That case is handled by the
`_committed`-gated mechanism in "The OAuth runtime" above, not by this
three-step algorithm — the two together are what make "start-of-run" mean
what table A promises, regardless of whether the token happened to need a
refresh at construction time or only revealed itself dead on the first real
request. Both routes end up calling `refresh_tokens()` and interpreting its
`DeadGrantError`/success/`ConfigError` outcomes the same way; only the
*moment* a dead grant is discovered differs.

**`[✓]` source of truth — split into a local-only read and a networked one,
because they answer different questions.** An earlier pass said the `[✓]`
marker is "always computed live, the same way `resolve_credentials()`
itself decides" — but `resolve_credentials()` can hit the network (the
60-second-margin refresh), and using that to render `init`'s provider
*list* would block the whole wizard on a slow or hung request just to draw
a checkbox. These are genuinely two different checks:

- **The `init` list's `[✓]` marker (local only, no network):** `tokens.toml`
  has an `[xai]` entry → `[✓] signed in as {email}` (or `[✓] signed in`,
  if `email` wasn't cached yet); else `env:`/`credentials:` resolves →
  `[✓] API key`; else unchecked. This does **not** distinguish a live token
  from a dead one — it can't, without a network call, so it doesn't try.
- **`init`'s grok branch (networked, once, only when the user actually
  selects/configures grok — see "Standalone login" for how this replaces
  the old "decline sign-in → paste-key" gap):** validate the stored token
  via the same refresh-or-check `resolve_credentials()`/`refresh_tokens()`
  path. Success → "already signed in" copy, no sign-in or paste-key prompt.
  `DeadGrantError` → treat as unsigned in, offer sign-in (and a pasted key
  *is* reachable, since the dead entry gets cleared). A transient
  `ConfigError` → show the "couldn't reach xAI" copy, offer **neither**
  sign-in nor paste-key this run (we don't know if the token's actually
  dead), and don't clear anything.

`auth = "oauth:xai"` written into config is, separately, for a human reading
`config.toml` only — it is **never** read by either `[✓]` check above or by
any resolution logic. `kadmon logout grok` (below) rewrites it; the
construction-time and mid-run dead-grant paths don't bother to, since
nothing reads it for behavior. It's written purely so the config file itself
is legible to a person reading it, not a second source of state to keep in
sync with the marker.

`kadmon logout grok`:
1. Delete the `[xai]` entry via `clear_tokens()`.
2. If `auth` was `"oauth:xai"`: set it to `env:XAI_API_KEY` if that env var is
   set, else clear it back to empty (falls back to the kind default, same
   `env:XAI_API_KEY`, as before OAuth existed).

Two idempotency edge cases, unspecified before now: `kadmon logout grok` with
no `[xai]` entry present is a **no-op**, not an error — logging out twice
isn't a failure. `kadmon login grok` while already signed in **overwrites**
the existing entry with no special-case handling — it's the same code path
as a fresh login, just against an account that happened to already have a
session; there's no "already signed in, skip" branch to maintain.

### Standalone login — `kadmon login grok` works with no prior `init`

`kadmon login grok` is a first-class entry point, not something that only
makes sense after `kadmon init`. It is responsible for creating the grok
provider entry itself if one doesn't exist yet:

1. `name` is a required positional argument. Only `grok` is valid in v1 —
   any other name: `OAuth sign-in is only available for xAI Grok in this
   version.`
2. Call `load_settings()`. If `settings.providers` has no `"grok"` entry,
   build one in memory: `kind="grok"`, `model=KIND_DEFAULTS["grok"]["model"]`
   (`grok-4.6`), `auth=""` (set after a successful test, per below). If a
   `"grok"` entry already exists, use it as-is except for `auth`, don't
   discard its `model`/`base_url` customization.
3. Run `auth.xai.device_login()` (no disk writes yet).
4. Build the override explicitly —
   `ResolvedCredentials(token=tokens.access_token, base_url=XAI_OAUTH_BASE_URL,
   headers=XAI_OAUTH_HEADERS)`, the same three values the `KIND_GROK` branch
   of `resolve_credentials()` would eventually produce from a saved token —
   and call `build_provider(grok_entry, max_tokens,
   credentials_override=creds)`. This runs the same `_test_provider`/
   `complete()` check every other provider gets, without needing a token
   that isn't saved yet, and without constructing `GrokProvider` directly.
   Login's call to `build_provider` must **not** get `XAIRefreshAdapter`
   wrapped around it (see the wrap table in "The OAuth runtime") — this is a
   one-shot test of a not-yet-persisted token, not a live run. Its own
   403/402/426 handling is the separate thin wrapper from "The shared
   mapper," not this adapter.
5. Only on success: call `auth.xai.save_tokens()`, set `grok_entry.auth =
   "oauth:xai"`, and persist the provider entry. Persisting means: take the
   **full** current provider list from `load_settings()`, replace or add the
   `"grok"` entry, and call `write_config(all_providers, default=...,
   path=GLOBAL_CONFIG_PATH)` — `write_config` rewrites the whole
   `[providers.*]` set from what it's given, so login must pass every
   existing provider, not just grok, or it silently drops the others.
   `default` stays whatever it already was, unless there were no providers
   configured at all before this, in which case set it to `"grok"`.
6. On failure at step 4: write nothing. Show the relevant Error states row.

**Config layering — the actual merge rule, not an assumption.** Providers
configured this way are written to the **global** config
(`GLOBAL_CONFIG_DIR`), matching where tokens already live, not the per-repo
`.kadmon/config.toml`. This only makes "`kadmon login grok` then `kadmon run`
from any directory" true because of how `load_settings()` already merges the
two files: it does `_merge(global_raw, project_raw)`, and `_merge` recurses
into any key present as a dict on both sides — so a `providers` table entry
defined only globally (like a freshly-added `grok`) passes through into the
merged settings untouched, and a project's own `.kadmon/config.toml` only
overrides it if that project *also* defines a `providers.grok` table of its
own. State this as the invariant a test should assert directly: a global-only
`grok` entry must be visible in `Settings.providers` when loaded from a repo
whose project config doesn't mention grok, and must **not** silently
disappear if the project config defines other providers without touching
grok.

After login, `kadmon run` uses grok automatically only if it's the sole
configured provider (today's `Settings.resolve()` behavior for a single
entry) or the configured `default`. With other providers already configured,
select grok explicitly (`--provider grok`) the same way you'd select any
other provider today — login does not change `default` unless nothing was
configured before.

### Factory / init

- Discovery: grok is "available" if a `tokens.toml` `[xai]` entry exists
  (regardless of whether it currently refreshes — surface the specific
  problem when the user actually tries to use it, per "Error states") **or**
  `env:`/`credentials:` resolves.
- New commands: `kadmon login <name>` and `kadmon logout <name>` — `name` is
  **required**, not optional, per "Standalone login" (only `grok` is valid in
  v1; other names get the "OAuth sign-in is only available for xAI Grok"
  message from that section). An earlier draft wrote `[name]` in brackets
  here, implying optional; that was wrong and is corrected.
- **Init's grok branch, the full algorithm.** "Decline sign-in → paste-key
  flow, unchanged" was true only when no token existed yet — a *live*
  `[xai]` entry means auth precedence's "a live token always wins" would
  make any key pasted in this `init` run silently unreachable. Distinguishing
  live from dead needs a network call, though, which is exactly why the
  `[✓]` list marker above stays local-only — this network check happens
  once, only when the user actually picks grok, not while rendering the
  list:
  1. Call `auth.xai.load_tokens()` then `refresh_tokens()` **directly** —
     not `resolve_credentials()`. This matters: `resolve_credentials()`
     *catches* `DeadGrantError` internally and turns it into a fallback or a
     raise, which is exactly the wrong shape for init — init needs to *see*
     the `DeadGrantError` itself to decide "offer sign-in," not have it
     already resolved into something else. If no `[xai]` entry exists at
     all: skip straight to offering sign-in (step 3's flow), no network
     call needed to know there's nothing to validate.
  2. Success → **do not offer the sign-in prompt at all.** Show `Signed in
     as {email}. Run \`kadmon logout grok\` to use an API key instead.` and
     treat grok as already configured.
  3. `DeadGrantError` → `clear_tokens()`, then offer sign-in exactly as
     before. This **is** "Standalone login" steps 3–6 (device flow → test
     via `credentials_override` → persist only on success), not a separate
     implementation — init just calls the same login routine. Decline →
     the paste-key flow, and a pasted key here **is** reachable, since the
     dead entry was just cleared.
  4. `ConfigError` with `status_code == 403` → **not** the transient case.
     Show the not-entitled copy (same as "Error states"). Keep the token.
     If the grok-only key lookup already finds a key, say so and use it; if
     not, offer the paste-key flow directly (writing a key here is
     reachable — a 403 doesn't invalidate the token, it just means OAuth
     inference won't work today, so the key path can coexist with it).
  5. `ConfigError` with any other status (timeout, 5xx, 429) → the
     genuinely transient case: show `Couldn't reach xAI to check your
     session. Try again, or run \`kadmon logout grok\` first if you want to
     switch to an API key.` and offer **neither** sign-in nor paste-key this
     run — we don't know the token is actually dead, so neither "already
     signed in" nor "let's sign in fresh" is honest, and the token stays on
     disk untouched.
- `_test_provider` still calls `complete()` — run it via
  `credentials_override`, against tokens not yet persisted (see "Standalone
  login"), whether the caller is `init` or `login` directly.

### Constraints (from AGENTS.md)

- No new framework. Provider SDKs plus stdlib `urllib` / a small OAuth helper.
- No `keyring` dependency in v1 — see "Token storage."
- No PyJWT or other JWT library — decode `id_token` claims with stdlib
  `base64` + `json` (see "Token storage").
- No `Any`, no `# type: ignore`.
- Tests mock **both** token hosts a real run touches: `auth.x.ai` (device
  code, token, refresh) and `cli-chat-proxy.grok.com` (inference). Do not hit
  either in CI.
- Everything still goes through `build_provider`. `kadmon login` calls
  `build_provider(..., credentials_override=...)` like everything else — it
  never constructs `GrokProvider` directly. `XAIRefreshAdapter`'s
  rebuild-with-a-fresh-token step lives inside `factory.py` too (see
  "Rebuild location" in "The OAuth runtime") — the AST guard doesn't get an
  exception for it.

## Open questions — resolved 2026-08-19

1. **Client identity — go.** `b1a00492-073a-47ea-816f-4c329264a828` is xAI's
   Grok CLI OAuth client. It shows up in `grok-build`'s own test fixtures
   (first-party confirmation) and is reused openly by many independent
   third-party projects (Hermes Agent, OpenCode's xAI plugin, Roo Code, and
   others), with no client secret — `token_endpoint_auth_methods_supported`
   includes `none`, i.e. it's a public client by design, the same trust model
   as `gcloud`'s or GitHub CLI's OAuth client ids. Use it; cite this provenance
   in the PR description in case anyone wants to sanity-check it later.
   **Considered and rejected: registering a dedicated Kadmon OAuth client.**
   xAI has no public self-service registration path for third-party OAuth
   clients (unlike, say, a Google Cloud or GitHub OAuth app registration
   flow) — the Grok CLI public client is the only available door, and it's
   the one every other independent OSS project in this space (Hermes, the
   OpenCode plugin, Roo Code, and others) also walks through. There is no
   more-legitimate alternative to reject in favor of; this is the only path.
2. **Flow — device-code for v1, browser PKCE deferred.** `auth.x.ai`'s OIDC
   discovery (`/.well-known/openid-configuration`) advertises
   `authorization_code`, `refresh_token`, and device-code grants, so both are
   available. Device-code is xAI's own first-party path for `grok-build` and
   works over SSH with no local callback listener — ship only that in v1.
   Browser PKCE is real future work, not "supported already," since it needs a
   loopback listener this pass doesn't build.
3. **Billing — confirmed, no surprise charge.** Warp's own docs
   (docs.warp.dev/agents/inference/grok-subscription) state OAuth usage draws
   from the same weekly pool as Grok Build and chat, and appears under an "API"
   label in the grok.com usage dashboard only because of *how* the request is
   made, not because it's billed separately. Safe to tell users: "no extra
   charge beyond your SuperGrok plan, subject to your weekly usage pool."
4. **Scope of v1 — unchanged.** Grok only.
5. **Keychain vs file — unchanged.** File-only (`~/.config/kadmon/tokens.toml`,
   mode 0600) is enough for v1.

New finding, not an original question but blocking either way: the OAuth
inference endpoint and required headers are different from the API-key path.
See "Wire constants" and "The credential contract" above — this changes
`GrokProvider`'s constructor, not just `resolve_credentials()`.

Known rough edge to design around, not to solve: xAI's own OAuth API surface
has been seen to 403 some valid SuperGrok subscribers regardless of client
(documented against Hermes Agent, issue #26847 in that project). This is not
a Kadmon bug and not fixable by retrying — it needs the "not entitled" row in
"Error states" above, not a bug report.

## Prior art to read first

- https://x.ai/news/grok-build-cli — first-party CLI, subscription login
- https://x.ai/news/grok-opencode — official "use SuperGrok inside OpenCode",
  xAI's own announcement of OAuth for a third-party open-source agent
- https://docs.warp.dev/agents/inference/grok-subscription/ — OAuth + weekly pool,
  confirms billing question
- https://github.com/NousResearch/hermes-agent/blob/main/website/docs/guides/xai-grok-oauth.md
  — device-code against `accounts.x.ai`; also documents the 403 tier-gate
  rough edge, tracked as issue #26847 in that repo
  (https://github.com/NousResearch/hermes-agent/issues/26847) — read this for
  the fallback-message case
- https://github.com/source-inc/gents/blob/main/docs/design-notes/xai-grok-oauth-spike.md
  — the most complete write-up found: OIDC discovery endpoints, the public
  client id verified against `grok-build`'s own test fixtures, the
  `cli-chat-proxy.grok.com` endpoint, and the required CLI-identity headers.
  The "Wire constants" and "Credential contract" sections above are copied
  from this source plus this doc's own verification — read the original
  before writing `GrokProvider`'s OAuth path, in case it's since been updated.

## Out of scope for v1

- Using Claude Pro / ChatGPT Plus / Gemini Advanced as API substitutes
- Cookie or unofficial web session reuse
- Changing the ReAct loop, tools, or streaming contract
- Making OAuth required (keys must keep working)
