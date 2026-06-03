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

## Horizon 1 — Build the cockpit

The engine already works; people bounce off the experience. This horizon makes Kadmon pleasant to
live in, and — critically — makes the differentiators *visible*. Highest leverage, mostly parity.

- `[parity]` **Rich terminal rendering.** Streamed markdown, syntax-highlighted code blocks, and a
  real **diff viewer** for edits and `submit` (today it just says "Patch generated (N lines)").
- `[parity]` **Tool activity UX.** Spinners/progress for long tool calls; clean, scannable
  start/result framing instead of dim text.
- `[parity]` **Input ergonomics.** Replace bare `input()` with a real line editor — history,
  multiline, in-line editing, paste handling, and graceful interrupt.
- `[parity]` **Slash commands.** `/help`, `/context`, `/clear`, `/model`, `/status`, `/checkpoints`,
  `/rewind`, `/cost`, `/handoff`, `/library` — session control without leaving the chat.
- `[parity]` **Streaming parity.** Add streaming to the OpenAI and Gemini providers (today only
  Anthropic/Bedrock stream); the loop already falls back gracefully, so this is provider work.
- `[parity]` **Cost & token display.** Surface the existing token accounting as a live, per-session
  cost summary.
- `[wedge]` **Make the wedge legible in the UI.** A live **context-budget meter** (how full, what
  will be dropped, when handoff triggers), a clear "handing off now" moment, and visible framing
  when the agent asks a directional question vs. acts on a mechanic.

## Horizon 2 — Sharpen the wedge

Turn the three pillars from architecture into advantages a user feels and a benchmark can measure.

### Context management — handoff, don't compact
- `[wedge]` **Handoff quality pass.** Tighten the brief the `HandoffAgent` produces (done / next /
  pointers), and make resume-from-handoff seamless and obvious to the user.
- `[wedge]` **Transparent context budgeting.** The Horizon-1 meter, deepened: let the user inspect
  exactly what's in context and what the next handoff will carry forward.
- `[wedge]` **Library introspection & continuity.** Commands to read/inspect the self-curating
  library; smooth the cross-session "pick up where yesterday left off" path.

### Autonomy — confidence-gated
- `[wedge]` **Sharpen confidence-gating.** Make the high/medium/low self-assessment that lives in
  the prompts a first-class, observable behavior: act on mechanics, ask on direction, always with
  options and the tradeoff stated.
- `[wedge]` **Better asking.** Strong question batching and presentation so directional questions
  are rare, clustered, and easy to answer.

### Trust — verification-first
- `[wedge]` **Wire the checkpoint inner loop.** `BacktrackManager` is built but not connected to the
  main loop. Integrate edit → test → on failure roll back → retry, autonomously, as the default
  recovery primitive.
- `[wedge]` **Verification as the gate.** Make "all detected checks pass" the condition for
  declaring work done, and show the evidence (what ran, what passed) in the UI.

### Proof
- `[wedge]` **Wedge metrics.** Define and track what we claim: context efficiency over long tasks,
  verified-completion rate, and questions-asked quality — so the edge is demonstrable, not asserted.

## Horizon 3 — Breadth & ecosystem

Close the remaining table-stakes breadth and open Kadmon to the ecosystem.

- `[parity]` **MCP support.** Consume external Model Context Protocol tool servers — now a
  near-universal expectation and currently absent.
- `[parity]` **Git workflow.** Beyond producing patches: branch management, well-formed commits, and
  PR creation, consistent with the project's conventional-commit rules.
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
