# Kadmon Roadmap

Inventory of what has shipped and what is still missing. **The order of unshipped
work is not decided.** Do not treat this file as the current queue.

North star: [VISION.md](VISION.md) (v2). How we score:
[docs/success-criteria.md](docs/success-criteria.md). Sign-in:
[docs/subscription-auth.md](docs/subscription-auth.md).

One use-blocker is already known, independent of the rest of the list: without
subscription sign-in, a SuperGrok user cannot run Kadmon without a second API
meter. That is not the same as “this file’s horizons are the plan.”

The Horizon 1–4 sections below are leftover sequencing from v1. Keep them as a
catalog of real gaps. Re-prioritize against Vision 2 before building them.
`[parity]` / `[wedge]` tags are historical labels from that document, not
current priority.

Status markers: `✅ shipped` (in `main`, verified). Unmarked = not done.
A line is done when the behavior is demonstrable, not when the code is written.

## Shipped

- ReAct loop, architect/editor, library team, dual-layer persistence, autonomous
  handoff, checkpoints/rewind/rollback, symbol index, parallel workers, eval
  harnesses (foundation).
- Transparent context + cost (`/context`, `/cost` with config-driven pricing).
- Input ergonomics (readline history + multiline).
- Repo-scoped git tool (no push/PR).
- Verification-first inner loop (rollback + retry on verify failure).
- Rich rendering (colored diffs + syntax-highlighted code blocks).
- In-chat slash commands.
- Streaming on Anthropic, Bedrock, OpenAI, Gemini, Grok.

## Horizon 1 — Build the cockpit

v1 inventory, not a queue. The engine already works; several cockpit items below have shipped.

The engine already works; people bounce off the experience. This horizon makes Kadmon pleasant to
live in, and — critically — makes the differentiators *visible*. Highest leverage, mostly parity.

- `[parity]` **✅ Rich terminal rendering.** Syntax-highlighted code blocks and a real **diff
  viewer** for edits and `submit` shipped (line-aware streaming: prose streams live, fenced code is
  rendered once, highlighted). Full streamed-markdown for prose remains a later refinement.
- `[parity]` **Tool activity UX.** Spinners/progress for long tool calls; clean, scannable
  start/result framing instead of dim text.
- `[parity]` **✅ Input ergonomics.** Bare `input()` replaced with readline history + in-line
  editing (persisted to `.kadmon/history`) and trailing-backslash multiline. Richer paste handling
  is a later refinement.
- `[parity]` **✅ Slash commands.** `/help`, `/clear`, `/status`, `/checkpoints`, `/model`, `/exit`,
  plus `/context` and `/cost` now shipped; `/rewind`, `/handoff`, `/library` later.
- `[parity]` **✅ Streaming parity.** All four providers (Anthropic, Bedrock, OpenAI, Gemini) now
  stream via a shared chunk contract.
- `[parity]` **✅ Cost & token display.** `/cost` shows per-session token accounting (always
  accurate); a dollar estimate appears only when model pricing is set in config (no hardcoded prices).
- `[wedge]` **✅ Make the wedge legible in the UI.** A live **context-budget meter** (`/context`:
  bar, utilization, token counts, near-handoff warning) shipped. The explicit "handing off now"
  moment and ask-vs-act framing follow.

## Horizon 2 — Sharpen the wedge

Turn the three pillars from architecture into advantages a user feels and a benchmark can measure.

### Context management — handoff, don't compact
- `[wedge]` **Handoff quality pass.** Tighten the brief the `HandoffAgent` produces (done / next /
  pointers), and make resume-from-handoff seamless and obvious to the user.
- `[wedge]` **✅/🔨 Transparent context budgeting.** The `/context` meter ships (used/max,
  utilization, near-handoff warning). Still to come: letting the user inspect exactly what the next
  handoff will carry forward.
- `[wedge]` **Library introspection & continuity.** Commands to read/inspect the self-curating
  library; smooth the cross-session "pick up where yesterday left off" path.

### Autonomy — confidence-gated
- `[wedge]` **Sharpen confidence-gating.** Make the high/medium/low self-assessment that lives in
  the prompts a first-class, observable behavior: act on mechanics, ask on direction, always with
  options and the tradeoff stated.
- `[wedge]` **Better asking.** Strong question batching and presentation so directional questions
  are rare, clustered, and easy to answer.

### Trust — verification-first
- `[wedge]` **✅ Wire the checkpoint inner loop.** On a failed `verify`, the loop rolls back to the
  edit tools' checkpoint and retries (capped, then falls back to recovery/handoff). Shipped.
- `[wedge]` **Verification as the gate.** Make "all detected checks pass" the condition for
  declaring work done, and show the evidence (what ran, what passed) in the UI.

### Proof
- `[wedge]` **Wedge metrics.** Define and track what we claim: context efficiency over long tasks,
  verified-completion rate, and questions-asked quality — so the edge is demonstrable, not asserted.

## Horizon 3 — Breadth & ecosystem

Close the remaining table-stakes breadth and open Kadmon to the ecosystem.

- `[parity]` **MCP support.** Consume external Model Context Protocol tool servers — now a
  near-universal expectation and currently absent.
- `[parity]` **✅/🔨 Git workflow.** A repo-scoped `git` tool ships with status/diff/log/branch/add/
  commit and safe defaults (no push/force/reset; hardened against option injection). PR creation
  still to come.
- `[parity]` **Wider symbol index.** Extend the tree-sitter index beyond Python/JS/TS to the
  languages Kadmon already benchmarks (Go, Rust, Java, C++).
- `[parity]` **Web & docs lookup.** A search/fetch capability so the agent can ground itself in
  current documentation.
- `[parity]` **Image/screenshot understanding.** Accept visual input (e.g. a failing UI, a diagram).
- `[parity]` **Model routing.** Cheap model for indexing/planning, strong model for editing/
  synthesis — extends the existing architect/editor split.
- `[parity]` **Hooks API.** User-defined pre/post lifecycle hooks; the session logger already gives
  a foundation.

## Horizon 4 — Frontier autonomy

Reach the autonomy surface the leaders are racing on — on our own local-first terms.

- `[parity]` **Background / async tasks.** Fire-and-forget a task, get notified on completion —
  without requiring a cloud.
- `[wedge]` **Deeper multi-agent orchestration.** Grow beyond `parallel_dispatch` into coordinated
  teams of scoped sub-agents, with handoff and the library as the shared-memory substrate (our
  answer to context blow-up that big-window/many-subagent approaches don't solve).
- `[parity]` **Optional local sandboxing.** Offer isolation for risky runs — offered, never
  required.

## Cross-cutting commitments

- **Eval is proof.** Score against [docs/success-criteria.md](docs/success-criteria.md), not
  against SWE-bench Verified or Polyglot as a headline.
- **Local-first, predictable cost.** Subscription sign-in where the vendor allows it; API key as
  fallback. No mandatory phone-home. Transparent token accounting.
- **Honest docs.** README and VISION stay accurate to what actually ships. This roadmap is an
  inventory, not a promise of order.

## What we are deliberately not doing

See [VISION.md](VISION.md#non-goals). In short: not an IDE, not cloud-mandatory, not
"minimize questions," not lossy compaction as the primary strategy, not a context brute-force
arms race, not user-maintained memory, not autonomy by silence.
