# Kadmon Roadmap

How we get from a mature engine with a bare cockpit to a state-of-the-art agent with a
defensible edge. This is the execution path behind [VISION.md](VISION.md); the landscape it
responds to is in [docs/design/competitive-analysis.md](docs/design/competitive-analysis.md).

## How to read this

- **No dates.** Horizons are ordered by leverage and dependency, not calendar. We execute fast;
  sequencing matters, estimates don't.
- **Two tracks run through every horizon.** `[parity]` items close the gap to table stakes;
  `[wedge]` items sharpen the three differentiators into visible, measurable advantages.
- **Grounded in today.** Each item names a real gap or a real piece of built-but-unfinished
  machinery. Nothing here is speculative architecture.
- A milestone is **done when it's verified** — tests pass and the behavior is demonstrable — not
  when the code is written.
- **Status markers:** `✅ shipped` (in `main`, verified), `🔨 in progress` (this batch), unmarked =
  not started. Items keep their `[parity]`/`[wedge]` tags.

## Status & progress

Newest first. Sequencing, not a changelog — see git history for detail.

- **🔨 In progress (this batch):** transparent context + cost budgeting (`/context` meter, `/cost`)
  `[wedge]`; input ergonomics (line editor) `[parity]`; git workflow tool `[parity]`.
- **✅ Shipped:** verification-first inner loop (rollback + retry on verify failure) `[wedge]`;
  rich rendering (colored diffs + syntax-highlighted code blocks) `[parity]`; in-chat slash commands
  `[parity]`; streaming parity across all four providers `[parity]`.
- **Foundation (pre-roadmap):** ReAct loop with architect/editor phases, library team, dual-layer
  persistence, autonomous handoff, checkpoints/rewind/rollback, symbol index, parallel workers,
  eval harnesses.

## Horizon 1 — Build the cockpit

The engine already works; people bounce off the experience. This horizon makes Kadmon pleasant to
live in, and — critically — makes the differentiators *visible*. Highest leverage, mostly parity.

- `[parity]` **✅ Rich terminal rendering.** Syntax-highlighted code blocks and a real **diff
  viewer** for edits and `submit` shipped (line-aware streaming: prose streams live, fenced code is
  rendered once, highlighted). Full streamed-markdown for prose remains a later refinement.
- `[parity]` **Tool activity UX.** Spinners/progress for long tool calls; clean, scannable
  start/result framing instead of dim text.
- `[parity]` **🔨 Input ergonomics.** Replace bare `input()` with a real line editor — history,
  multiline, in-line editing, paste handling, and graceful interrupt.
- `[parity]` **✅ Slash commands.** `/help`, `/clear`, `/status`, `/checkpoints`, `/model`, `/exit`
  shipped; `/context`, `/cost` landing this batch; `/rewind`, `/handoff`, `/library` later.
- `[parity]` **✅ Streaming parity.** All four providers (Anthropic, Bedrock, OpenAI, Gemini) now
  stream via a shared chunk contract.
- `[parity]` **🔨 Cost & token display.** Surface per-session token accounting (always accurate) as
  a live summary; optional cost estimate when model pricing is configured (no hardcoded prices).
- `[wedge]` **🔨 Make the wedge legible in the UI.** A live **context-budget meter** (how full, how
  close to the handoff threshold) via `/context`; the "handing off now" moment and ask-vs-act
  framing follow.

## Horizon 2 — Sharpen the wedge

Turn the three pillars from architecture into advantages a user feels and a benchmark can measure.

### Context management — handoff, don't compact
- `[wedge]` **Handoff quality pass.** Tighten the brief the `HandoffAgent` produces (done / next /
  pointers), and make resume-from-handoff seamless and obvious to the user.
- `[wedge]` **🔨 Transparent context budgeting.** The Horizon-1 meter, deepened: let the user inspect
  exactly what's in context and what the next handoff will carry forward. (Backend stats + `/context`
  meter land this batch; "what handoff carries forward" follows.)
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
- `[parity]` **🔨 Git workflow.** Beyond producing patches: status/diff/branch/log and well-formed
  commits (a repo-scoped `git` tool with safe defaults — no push/force/reset). PR creation follows.
  Pulled forward as clean, independent parity work.
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

- **Eval is proof.** Keep the Polyglot and SWE-bench harnesses green and use them as the public
  measure of coding ability; pair them with the wedge metrics from Horizon 2.
- **Local-first, predictable cost.** BYO-key, no mandatory phone-home, transparent token accounting.
  As competitors move to opaque usage credits, this is a feature.
- **Honest docs.** README, VISION, and this roadmap stay accurate to what actually ships. We don't
  document aspirations as features.

## What we are deliberately not doing

See [VISION.md](VISION.md#non-goals-so-we-stay-grounded) for the full list. In short: not an IDE,
not cloud-mandatory, not "minimize questions," not lossy compaction as the primary strategy, not a
context brute-force arms race, not user-maintained memory, not autonomy by silence.
