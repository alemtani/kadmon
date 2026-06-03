# Differentiators — Design Note

The wedge, grounded in code. [VISION.md](../../VISION.md) states *why* the three pillars matter and
[ROADMAP.md](../../ROADMAP.md) sequences the work; this note connects each pillar to the **actual
components** that implement it today, what "sharpened" looks like, and how we'll know it worked.

The point of writing it down: these are not features to bolt on later. They are the architecture
Kadmon was built around. The work is mostly to *finish wiring* and *make visible* what already
exists.

---

## Pillar 1 — Context management: graceful handoff

### What exists today
- `kadmon/agent/handoff.py` — `HandoffMonitor` detects when to hand off (token budget ~80%,
  quality degradation via repeated loop recoveries, or a "clean break" between work areas) and
  `HandoffManager` crafts the brief, persists it to `docs/handoffs/latest.md`, and resets context.
- `kadmon/memory/agents/handoff_agent.py` — `HandoffAgent` synthesizes the brief with an LLM
  (with a deterministic fallback).
- `kadmon/agent/context.py` — token-budget-aware message manager (currently a `char/4` estimate;
  truncates oversized tool results).
- The **library team** (`kadmon/memory/agents/`: Index, Read, Write, Prune, Curator) — the
  self-curating memory that gives cross-session continuity, plus the JSONL flight recorder
  (`kadmon/memory/session_log.py`) and cross-project index (`kadmon/memory/central_index.py`).

### Why it's differentiated
Every competitor responds to context limits with lossy compaction (Claude Code's three-tier
cascade), per-task isolation (Codex, Cursor), or brute-force windows (Gemini's 1M). None do an
explicit **write-brief → reset → continue** cycle. Compaction is documented to lose early
instructions and re-ask resolved decisions; handoff is designed to carry exactly the decisions and
pointers forward and drop the noise.

### Sharpened form
- A tighter, more reliable brief (done / next / key pointers) that a fresh context can act on
  immediately.
- A **transparent context budget** the user can see — fullness, what will be dropped, when handoff
  triggers — so the strategy is legible instead of a black box.
- A real tokenizer behind the budget estimate, so the meter is trustworthy.
- Seamless, obvious resume-from-handoff and "pick up yesterday's work" via the library.

### How we measure it
- **Context efficiency on long tasks:** quality holds across a handoff boundary (no regression in
  verified-completion) at materially lower peak token usage than a compaction baseline.
- **Decision retention:** resolved directional questions are not re-asked after a handoff.

---

## Pillar 2 — Autonomy: confidence-gated

### What exists today
- `kadmon/agent/prompts.py` — `SYSTEM_PROMPT` / `ARCHITECT_PROMPT` / `EDITOR_PROMPT` encode a
  high/medium/low confidence framework: act on mechanics, surface uncertainty on direction.
- `kadmon/tools/ask_human.py` + `kadmon/human/` — `ask_human` is a *tool* the agent reaches for,
  not a permission mode the user configures; `QuestionBatcher` clusters questions; CLI and webhook
  channels deliver them.
- `kadmon/agent/loop.py` — the architect/editor phase separation that lets the agent plan before it
  executes.

### Why it's differentiated
The industry models autonomy as a dial the *user* sets (Codex's four approval modes, Cline's
plan/act, "full-auto"). Kadmon flips the axis: the *agent* self-assesses per action. It never asks
permission for `mkdir`; it does ask when a requirement is ambiguous or a design could go two ways.
No competitor implements confidence-gated asking as an autonomous behavior.

### Sharpened form
- Make the high/medium/low self-assessment an **observable** behavior, not just prompt guidance —
  visibly act on mechanics, visibly ask (with options + tradeoff) on direction.
- Questions that are rare, clustered, and decision-shaped ("REST or GraphQL, here's the tradeoff"),
  never mechanical ("can I edit this file?").

### How we measure it
- **Questions-asked quality:** ratio of directional questions to mechanical ones trends to ~all
  directional; total interruptions per task trend down while *wrong-direction* rework also trends
  down.
- **Trust proxy:** tasks completed end-to-end without a human approving mechanics.

---

## Pillar 3 — Trust: verification-first

### What exists today
- `kadmon/qa.py` + `kadmon/tools/verify.py` — multi-scope QA runner that auto-detects the project's
  test/lint tooling (pytest, npm, cargo, go, gradle, maven) and runs it.
- `kadmon/checkpoints.py` + `kadmon/tools/checkpoint.py` — file snapshots before edits with
  rollback; `kadmon/conversation.py` — conversation rewind.
- `kadmon/agent/recovery.py` — `LoopDetector` catches repeated tool calls/errors and injects a
  recovery prompt.
- `kadmon/agent/backtrack.py` — `BacktrackManager` for checkpoint-aware step retry.

### The honest gap
`BacktrackManager` is **built but not wired** into `loop.py` — the loop currently uses
`LoopDetector` + handoff, not the full edit → test → fail → rollback → retry primitive. Verification
runs when invoked, but "all checks pass" is not yet the hard gate for declaring work done. Closing
both is the core of the trust pillar.

### Why it's differentiated
Codex runs tests in its sandbox and Claude Code can enforce checks via hooks, but no agent makes
**verified completion the definition of done**, and none expose an autonomous
edit→test→rollback→retry inner loop as a first-class primitive. Most agents will present code that
doesn't run.

### Sharpened form
- Wire `BacktrackManager` into the loop so routine recovery (a failing test) is handled
  autonomously: roll back to the last good checkpoint, try differently, no human needed.
- Make verification the **gate**: the agent does not declare "done" until detected checks pass, and
  it **shows the evidence** (what ran, what passed) in the UI.

### How we measure it
- **Verified-completion rate:** fraction of "done" claims where the project's checks actually pass —
  target ~100%.
- **Autonomous recovery rate:** fraction of test failures resolved by the inner loop without human
  intervention.

---

## The shape of the wedge

| Pillar | Built today | The unfinished edge | The metric |
|--------|-------------|---------------------|------------|
| Context | handoff monitor/manager/agent, library team, flight recorder | tighter brief + **transparent budget** + real tokenizer | context efficiency, decision retention |
| Autonomy | confidence-gated prompts, `ask_human` tool, batching | make self-assessment **observable**; sharper questions | questions-asked quality |
| Trust | QA runner, checkpoints, rewind, loop detector | **wire BacktrackManager**; make verification the **gate** | verified-completion, autonomous recovery |

Parity (the cockpit) earns the look. This wedge earns the switch.
