# Kadmon

**A teammate coding agent.** You give it a Task or a Project. It asks when direction is unclear, proves the work, and uses the subscription you already pay for.

## Why Kadmon exists

Agents that only go fast guess on direction and forget on long work. Agents that only go safe ask permission to edit a file. Kadmon is the teammate in between: autonomous on mechanics, explicit on direction, and "done" only when the repo's checks pass.

A **Task** comes back as a PR. A **Project** stops for a design YES/NO, then those PRs. It writes skills that fire the next time on this repo.

## Vision & Roadmap

- **[VISION.md](VISION.md)** — north star (v2, August 2026).
- **[docs/success-criteria.md](docs/success-criteria.md)** — how we score it (workplace + public comparison).
- **[docs/subscription-auth.md](docs/subscription-auth.md)** — sign in with the subscription you already pay for.
- **[ROADMAP.md](ROADMAP.md)** — shipped work and known gaps. Order of unshipped work is not decided.
- **[docs/design/competitive-analysis.md](docs/design/competitive-analysis.md)** — landscape (historical; some cockpit gaps listed there have since shipped).

## Install

```bash
npm install -g kadmon
```

Or with pip:
```bash
pip install kadmon
```

## Getting Started

```bash
kadmon init
```

This walks you through provider setup once (globally — not per-project). Then in any project:

```bash
cd your-project
kadmon
```

Type your task, kadmon works, streams output as it goes. Ctrl+C to exit.

### Updating

```bash
pip install --upgrade kadmon
```

Or with npm:
```bash
npm update -g kadmon
```

### Provider Setup (manual alternative to `kadmon init`)

**xAI Grok:**
```bash
export XAI_API_KEY=xai-...
kadmon --provider grok
```

**Anthropic:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
kadmon --provider anthropic
```

**OpenAI:**
```bash
export OPENAI_API_KEY=sk-...
kadmon --provider openai
```

**Google Gemini:**
```bash
export GOOGLE_API_KEY=...
kadmon --provider gemini
```

**AWS Bedrock:**
```bash
export AWS_PROFILE=your-profile
export AWS_REGION=us-east-1
kadmon --provider bedrock
```

`kadmon init` writes `~/.config/kadmon/config.toml`. A project can overlay that with `.kadmon/config.toml`. You can configure several providers and switch with `--provider`.

## What Makes Kadmon Different

Other agents are either fast-but-reckless (YOLO mode, guess and go) or safe-but-slow (approve every file write). Kadmon is neither. It's fully autonomous on mechanics — but asks you when it's genuinely uncertain about direction.

### YOLO on execution, deliberate on decisions

Kadmon never asks "can I edit this file?" or "should I run this test?" — it just does it. But when requirements are ambiguous, when a design could go two ways, when it's not sure what you actually want — it asks. This is what makes it trustworthy enough to run unsupervised.

### Self-managing context

Most agents degrade over long sessions. Context fills up with irrelevant tool outputs, the model starts looping, quality drops. You restart, lose everything, re-explain the task.

Kadmon detects this happening and handles it:
1. Writes a focused handoff document (what's done, what's next, key pointers)
2. Clears its own context
3. Continues from the handoff — no human intervention needed

### Persistent memory across sessions

Kadmon maintains a project library (`.kadmon/library/`) that survives across sessions:
- Architecture notes, conventions, decisions — written by the agent, not by you
- Mechanical session logging captures everything (flight recorder)
- LLM-powered curation synthesizes raw logs into clean knowledge between sessions
- Cross-project session index so kadmon knows what you were working on yesterday

### Checkpoints and rewind

Made a wrong turn? Two escape hatches:
- `kadmon rewind` — go back to before any recent prompt (conversation reset, files untouched)
- `kadmon rollback` — undo file changes to any checkpoint

The agent also uses checkpoints autonomously: edit → test → fail → rollback → try differently. No human intervention needed for routine recovery.

## Commands

```bash
kadmon                    # Interactive chat (default)
kadmon continue           # Resume previous task from where you left off
kadmon status             # Show current session and library state
kadmon status --global    # Show recent sessions across all projects
kadmon rewind             # Rewind conversation to a previous prompt
kadmon rollback [id]      # Rollback file changes to a checkpoint
kadmon checkpoints        # List available file checkpoints
kadmon init               # Interactive provider setup
kadmon run --task "..."   # One-shot mode
```

## Architecture

```
kadmon/
├── agent/       # ReAct loop, planning, handoff, recovery
├── providers/   # LLM providers (Bedrock, Anthropic, OpenAI, Grok, Gemini)
├── tools/       # file I/O, search, shell, plan, ask_human, library, checkpoints, parallel
├── memory/      # Library team (index/read/write/prune/curator agents), session log
├── human/       # Question batching, CLI/webhook channels
├── workers.py   # Parallel task dispatch (ThreadPoolExecutor)
├── checkpoints.py  # File-level snapshots for rollback
├── conversation.py # Conversation state for rewind
├── eval/        # Benchmark harnesses (Aider Polyglot, SWE-bench)
└── index/       # Tree-sitter symbol index (SQLite)
```

Key design:
- **Architect/Editor phase separation** — explore and plan first, then execute step by step
- **Library Team** — focused LLM subagents for on-demand context retrieval (not blob injection)
- **Dual-layer persistence** — mechanical capture (JSONL flight recorder) + intelligent curation (LLM synthesis)
- **Autonomous handoff** — detects context degradation, writes handoff, resets, continues
- **Parallel workers** — fan out independent subtasks to separate context windows
- **No frameworks** — provider SDKs directly, minimal core
- **ask_human as a tool** — always available for genuine uncertainty, never for permission

## Philosophy

Kadmon optimizes for **trust**, not speed.

The bet: developers give more autonomy to an agent that asks "should this be REST or GraphQL?" before building the wrong thing — and then proves it works with passing tests — than to one that silently builds the wrong thing fast.

Trust compounds. An agent that asks good questions and verifies its work earns the right to run unsupervised on bigger tasks. An agent that guesses and sprints earns Ctrl+C.

## Local Development

```bash
git clone https://github.com/ayuan153/kadmon.git
cd kadmon
./dev
```

`./dev` handles everything: creates a venv, installs dependencies, and launches kadmon from your local source.

```bash
./dev              # Launch interactive kadmon (local build)
./dev bench        # 5 Python exercises
./dev bench 20     # 20 exercises
./dev bench-full   # All 225 exercises, 6 languages
./dev run "task"   # One-shot mode
./dev test         # Run tests
./dev lint         # Run linter
```

## Benchmarking

### Aider Polyglot

225 Exercism exercises across Python, JavaScript, Go, Rust, Java, C++.

```bash
kadmon bench --languages python --limit 5   # Quick smoke test
kadmon bench --languages python              # Full Python
kadmon bench -j 10                           # All languages, parallel
```

### SWE-bench

```bash
kadmon eval --dataset swe_bench_verified_mini.json --limit 10
```

## Contributing

See [AGENTS.md](AGENTS.md) for AI contribution guidelines. Key rules:
- Build → Lint → Test → Commit (no skipping)
- Conventional commits with scopes
- One concern per commit

## Publishing

```bash
./publish          # patch: 0.4.0 → 0.4.1
./publish minor    # minor: 0.4.1 → 0.5.0
./publish major    # major: 0.5.0 → 1.0.0
```

Bumps version, commits, tags, pushes. CI publishes to PyPI + npm automatically.

## License

MIT
