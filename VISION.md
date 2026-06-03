# Kadmon Vision

**YOLO mode you can trust.** Kadmon is an autonomous coding agent that manages its own
context, asks the right questions, and proves its work — so a developer can hand it real work
and walk away, not babysit it.

This document is the north star. For the current landscape see
[docs/design/competitive-analysis.md](docs/design/competitive-analysis.md); for the path of
execution see [ROADMAP.md](ROADMAP.md).

## The bet

Coding agents have gotten very capable and very fast. The thing holding them back from real
autonomy isn't raw coding skill — it's that they **lose the plot**: they fill their context and
forget, they guess on ambiguous decisions instead of asking, and they hand you work that doesn't
actually run. Each of those erodes trust, and without trust you can't leave an agent alone.

Kadmon's bet is that **trust is the scarce resource**, and trust is earned three ways:

1. **It doesn't forget.** Context is managed by graceful handoff, not lossy compaction.
2. **It asks about the right things.** Full autonomy on mechanics; it speaks up on direction.
3. **It proves its work.** Verification is the gate for "done," not an optional extra.

An agent that does these earns the right to run unsupervised on bigger and bigger tasks. Trust
compounds. That compounding is the whole game.

## Where we are

Kadmon's engine is real and mature: a ReAct loop with architect/editor phases, a six-agent
library team for memory, dual-layer persistence, autonomous handoff, checkpoints and rollback, a
symbol index, parallel workers, multi-provider support, and a real eval harness.

What's missing is twofold, and we're honest about it:

- **The cockpit is bare.** Streaming text and colored markers, no real TUI, no diff viewer, no
  syntax highlighting, no input ergonomics. The engine is a race car; the dashboard is a light
  bulb.
- **Some breadth is missing.** No MCP, partial streaming, a git workflow gap, no web or image.

So the vision has two movements: **reach the bar, then move it.**

## The north star: parity, then wedge

### Movement 1 — Reach the bar (parity)

A developer evaluating Kadmon should never bounce off a missing table-stakes feature. The agentic
substrate is already competitive; the experience around it must be too. That means a genuinely good
terminal cockpit, slash commands, reviewable diffs, MCP, a real git workflow, streaming on every
provider, and visible cost. None of this is novel — all of it is necessary. Parity is the price of
being considered at all.

### Movement 2 — Move the bar (wedge)

Parity gets us in the room. We win on three things no competitor does well, each mapping to a
pillar below. These are not features bolted on — they're the architecture Kadmon was built around,
and the work is to sharpen them into advantages a user can *see* and a benchmark can *measure*.

## The three pillars

### Pillar 1 — Context management: hand off, don't compact

Every leading agent eventually hits its context limit and responds with lossy summarization, or
sidesteps it with brute-force giant windows and per-task isolation. Summarization is documented to
drop early instructions, re-ask resolved decisions, and stall on the summary call. Bigger windows
delay the problem and make it more expensive; they don't solve forgetting.

Kadmon's answer: **detect the moment context is degrading, write a focused handoff brief (what's
done, what's next, the key pointers), reset to a clean context, and continue from the brief.** A
fresh start with surgical context beats a bloated, lossy summary. The same machinery gives Kadmon
something rarer still — **continuity across sessions**: a self-curating library where LLM subagents
distill raw session logs into pruned, reusable project knowledge, so the agent that picks up
tomorrow knows what yesterday's agent learned. Locally. Without the user maintaining a memory file.

**The north-star feeling:** long tasks don't degrade, and the agent remembers your project the way
a teammate would.

### Pillar 2 — Autonomy: fast on mechanics, deliberate on direction

The industry frames autonomy as a dial the user sets: approve everything, approve some things,
approve nothing. That's the wrong axis. Developers don't want to approve `mkdir` and `git add` —
and they don't want the agent to silently guess whether the API should be REST or GraphQL.

Kadmon's answer: **confidence-gated autonomy.** The agent self-assesses before acting. High
confidence on a mechanical step → just do it. Genuine uncertainty about *direction* — ambiguous
requirements, a design that could go two ways, a tradeoff the user should own → it stops and asks,
with the options and the tradeoff laid out. `ask_human` is a tool the agent reaches for when it's
uncertain, not a permission gate the user configures. This is what makes full autonomy trustworthy:
it sprints on execution and surfaces the decisions that are actually yours.

**The north-star feeling:** it never interrupts you for busywork, and it never builds the wrong
thing in silence.

### Pillar 3 — Trust: prove it, or it isn't done

Most agents will happily present code that doesn't compile. Verification exists but is optional —
a hook you configure, a test you remember to ask for. Trust can't be built on "probably works."

Kadmon's answer: **verification-first.** The agent scouts how the project is tested, and "all
checks pass" is the gate for declaring work done — not a nice-to-have. Recovery is built into the
inner loop: edit → test → on failure, roll back to a checkpoint and try differently, autonomously,
without a human in the loop for routine recovery. And the whole run is legible — what's in context,
what it's about to do, what it verified — because trust requires being able to see what happened.

**The north-star feeling:** when Kadmon says "done," it ran, and you can see the proof.

## What winning looks like

- A developer hands Kadmon a multi-step task, closes the laptop, and comes back to **working,
  verified** changes — or a small set of **sharp questions** that genuinely needed a human.
- Long sessions **don't rot.** Kadmon hands off to itself and keeps going at full quality.
- The next day, Kadmon **remembers the project** without being re-briefed.
- On the standard benchmarks (Polyglot, SWE-bench) Kadmon is competitive — and on the things we
  care about (context efficiency, verified-completion rate, questions-asked quality) it is
  measurably ahead.
- It runs **local-first**, on the model you choose, with costs you can see.

## Non-goals (so we stay grounded)

- **Not an IDE.** Kadmon is terminal-first. We integrate with editors; we don't become one.
- **Not cloud-mandatory.** No required phone-home, no forced sandbox-in-the-cloud. Local-first is a
  feature, not a limitation. (We may *offer* sandboxing; we won't *require* a cloud.)
- **Not "minimize questions."** We ask *fewer, better* questions — not zero. An agent that never
  asks is an agent that builds the wrong thing fast.
- **Not lossy compaction as the primary strategy.** Handoff is the answer to context limits.
- **Not a 1M-window or 1K-subagent arms race.** We win on context *intelligence*, not context
  *brute force*.
- **Not user-maintained memory.** The library is self-managing. We don't regress to asking the user
  to curate a memory file.
- **Not autonomy by silence.** Speed without verification is gambling; we don't ship it as a virtue.

## The through-line

Other agents optimize for speed (ask less) or safety (gate everything) or scale (bigger windows,
more subagents). Kadmon optimizes for **trust** — the one thing that lets a developer actually let
go. We reach parity so we're in the conversation, and we sharpen the wedge so we win it: the agent
that doesn't forget, asks the right questions, and proves its work.
