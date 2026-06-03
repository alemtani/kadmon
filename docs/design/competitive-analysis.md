# Competitive Analysis — SOTA Coding Agents

> Snapshot of the coding-agent landscape and where Kadmon fits. Read alongside
> [VISION.md](../../VISION.md) (where we're going) and [ROADMAP.md](../../ROADMAP.md) (how we get there).
> Last refreshed: mid-2026. Sources for the underlying research are tracked in the design notes.

## TL;DR

The market has converged on a common feature floor — agentic loop, multi-file edits with
diff review, MCP, a project instructions file, slash commands, plan mode, streaming, multiple
models. Leaders now differentiate on **autonomy surface** (background/async agents, multi-agent
orchestration) and **scale** (1M-token windows, thousands of subagents).

Kadmon's engine already clears most of the *capability* floor. Where it falls short is the
**cockpit** (UX, ergonomics, presentation) and a few breadth items (MCP, git workflow, web).

What no competitor does well — and what Kadmon is architected around — is **context management
that doesn't lose information, autonomy that knows when to ask, and trust earned through
verification.** That is the wedge.

## The landscape at a glance

| Agent | Surface | Context strategy | Autonomy model | Trust mechanism | Distribution |
|-------|---------|------------------|----------------|-----------------|--------------|
| **Claude Code** | CLI + IDE + web | 1M window + 3-tier auto-compaction (lossy) | Fully autonomous + granular permissions; hooks; Agent Teams; up to 1K subagents | Hooks enforce lint/test; relies on git | Sub ($20–200/mo) + API |
| **Cursor** | IDE + CLI | `.cursor/rules` + embeddings; per-agent task scoping | Agent mode default; cloud agents in isolated VMs; event automations | Diff review (Composer); BugBot PR review; sandboxed VMs | Sub ($20–40/mo) + credits |
| **OpenAI Codex** | CLI (Rust, OSS) + cloud | AGENTS.md; cloud task = fresh sandbox per repo | 4 approval modes (suggest→full-auto); multi-agent parallel | OS-level sandbox; **auto-review agent**; runs tests before PR | ChatGPT sub + compute credits; CLI is MIT |
| **Gemini CLI** | CLI (OSS) | Brute-force 1M window; GEMINI.md | Agentic loop; MCP; Jules extension for async delegation | Local, approval for destructive cmds | **Free 1K req/day**; OSS client |
| **Aider** | CLI (OSS) | Repo map (tree-sitter); **manual** /add /drop | Architect/editor split; autonomous within a request | **Git-native** (every edit = commit); polyglot leaderboard | OSS, BYO-key |
| **Cline / Roo Code** | VS Code (OSS) | Plan/Act gathers context upfront; MCP retrieval | Plan→approve→Act; configurable auto-approve | **Checkpoints**; visible focus chain; diff review | OSS, BYO-key |
| **Windsurf** | IDE | Flow engine; auto-generated **Memories**; rules | Cascade multi-file; repeatable Workflows | Inline diff review; git for undo | Sub ($15–60/mo) |
| **Devin** | Cloud (async) | Own long-lived environment per session | Fire-and-forget; parent/child sessions for multi-day work | Full sandbox; runs tests | **ACU usage** (~$2.25/unit) |
| **Jules** | Cloud (async) | Cloud VM per task | Fire-and-forget → PR | Cloud VM; runs tests | Free tier + paid |
| **Copilot** | IDE + cloud | Repo context; per-task model choice | Agent mode + async coding agent | PR review flow | Token-based credits (2026 billing drew backlash) |

## What is now table stakes

A coding agent is no longer credible without:

- Agentic loop (plan → act → observe → iterate)
- Multi-file editing **with reviewable diffs**
- Shell execution and output observation
- A project instruction file (AGENTS.md / CLAUDE.md / .cursorrules) — Kadmon supports AGENTS.md
- MCP (Model Context Protocol) for external tools — **Kadmon gap**
- Slash commands for session control — **Kadmon gap**
- Plan mode / reason-before-execute — Kadmon has architect/editor phases
- Multiple model/provider support — Kadmon supports 4
- Streaming output — Kadmon streams on Anthropic/Bedrock only (**partial gap**)
- Git integration (commit, branch) — **Kadmon partial** (produces patches, no workflow)

**Emerging** (not yet universal but trending): background/async agents, parallel task execution,
checkpoints/rollback (Kadmon has this), persistent cross-session memory (Kadmon has this), and a
plugin/MCP ecosystem.

## How the leaders handle the three things we care about

### Context management
The norm is **lossy compaction**: when the window fills, summarize and continue. Claude Code runs
a three-tier cascade (strip stale tool results → LLM-summarize the conversation → use pre-extracted
notes). Cursor and Codex sidestep it with per-task isolation (each agent/task gets a fresh window).
Gemini CLI brute-forces it with a 1M window. Aider and Cline push the work onto the user (manually
add/drop files, or gather context upfront in plan mode).

Documented failure modes of compaction are consistent across reports: early instructions drift and
get lost, resolved decisions get re-asked, the summarization call stalls inference, and there is no
guarantee critical detail survives. The mechanism meant to preserve context actively discards it.

**No agent does an explicit, autonomous handoff** — write a structured brief, reset to a clean
context, and continue from the brief. That is exactly Kadmon's approach, and it is open white space.

### Autonomy
There is a clear spectrum from per-action approval (Cline) → mode-based (Codex's four modes) →
fully autonomous on mechanics (Claude Code, Cursor agent) → fire-and-forget async (Devin, Jules,
Copilot coding agent). Multi-agent orchestration is the frontier (Claude's up to 1K subagents,
Codex parallel agents, Cursor multiple background agents).

But autonomy is uniformly framed as a **permission setting** the user dials. **No agent
self-regulates by confidence** — going fast on mechanics while proactively asking the human when it
is genuinely uncertain about *direction*. Claude Code can ask a human, but it is not confidence-gated
behavior. This is Kadmon's wedge.

### Trust / verification
Codex leads here: an OS-level sandbox plus a separate **auto-review agent** that approves or denies
boundary-crossing actions, and it runs tests in the sandbox before proposing a PR. Claude Code uses
hooks to deterministically enforce lint/test after edits. Cline offers checkpoints. Everyone else
leans on git and human PR review.

**No agent makes "all tests pass" the gate for presenting work.** Verification is available but
optional; it is not the spine of the loop. Kadmon's verification-first design — refuse to present
work that doesn't pass — is differentiated.

## Where Kadmon stands today (honest)

Kadmon's architecture is mature and its README is substantially accurate. Working today: full ReAct
loop with architect/editor phase separation; 18 functional tools; 4 providers; a six-agent library
team (index/read/write/prune/curator/handoff); dual-layer persistence (JSONL flight recorder + LLM
curation); autonomous handoff on token budget / quality degradation / clean break; checkpoints,
rewind, and rollback; a tree-sitter symbol index; SWE-bench and Polyglot eval harnesses; ten CLI
subcommands; ~230 tests.

The honest gaps are in two buckets:

**Cockpit (the dominant gap).** The UI is streaming text plus colored tool markers. There is no
TUI, no diff viewer, no syntax highlighting, no markdown rendering, no spinners/progress, and input
is a bare `input()` with no history, multiline, or editing. The engine works; the cockpit is bare
metal.

**Breadth.** No MCP. Streaming only on Anthropic/Bedrock. Symbol index limited to Python/JS/TS. No
git workflow (branch/commit/PR). No web or image capability. No user-facing cost display.
`BacktrackManager` is built but not wired into the loop.

## White space — Kadmon's wedge

These align directly with the three pillars and are under-served by everyone:

1. **Graceful handoff instead of lossy compaction.** Nobody does autonomous write-brief → reset →
   continue. Fresh context beats a degraded summary.
2. **Confidence-gated autonomy.** Fast on mechanics, asks on directional uncertainty — as a
   behavior, not a user-configured mode.
3. **A self-curating living library.** LLM subagents synthesize raw logs into pruned knowledge.
   CLAUDE.md is static; Windsurf Memories are auto-generated but not curated.
4. **Checkpoint + rollback as an autonomous inner-loop primitive.** Edit → test → fail → rollback →
   retry without human intervention.
5. **Verification-first.** "Prove it with tests" is the gate, not an afterthought.
6. **Transparent context budgeting.** Show what's in context, what will be dropped, when handoff
   triggers — the opposite of opaque compaction.
7. **Predictable, local-first operation.** As competitors move to opaque usage credits, a BYO-key,
   no-phone-home agent with transparent token accounting is increasingly attractive.

## Positioning vs each leader

- **vs Claude Code** — We won't match a 1M window or 1K subagents. Win on context *efficiency*
  (handoff > compaction), verification-first, and predictable local-first operation.
- **vs Cursor** — Terminal-first, not IDE-locked. Win on transparency and long-task context
  management.
- **vs Codex** — Shared sandbox/verify philosophy. Win on local-first (no cloud required),
  persistent memory, and handoff continuity.
- **vs Gemini CLI** — They have 1M free context. Win on context *intelligence* (handoff when
  needed), verification loops, and persistent project knowledge.
- **vs Aider** — Closest in spirit (git-native, terminal, BYO-key). Win on autonomous context
  management, parallel workers, and verification-first.

## Implications

Two tracks, detailed in [ROADMAP.md](../../ROADMAP.md):

- **Parity track — build the cockpit.** A real TUI, diff/syntax rendering, slash commands, input
  ergonomics, MCP, git workflow, streaming parity, cost display. This is catch-up and it is mostly
  presentation, not architecture.
- **Wedge track — sharpen the differentiators** into visible, benchmarkable advantages: handoff,
  confidence-gating, the living library, the verification-first loop, and transparent context
  budgeting.

We catch up on the cockpit so users stay; we pull ahead on the wedge so they switch.
