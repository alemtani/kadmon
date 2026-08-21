# Kadmon Vision

**Version 2 · August 2026.** This is the north star. Measurement: [docs/success-criteria.md](docs/success-criteria.md). Sign-in: [docs/subscription-auth.md](docs/subscription-auth.md). Execution: [ROADMAP.md](ROADMAP.md). Previous north star: [docs/design/vision-v1.md](docs/design/vision-v1.md).

Kadmon is a teammate coding agent. You tell it what to do. You do not tell it which files to open. It asks when direction is unclear. It ships through the same gates a coworker would.

## Work units

A **Task** is one pull request. Tests on that PR are green. An independent review exists. You merge or you don't.

A **Project** is a design you accept or reject, then those Tasks. Implementation does not start before YES. Long Projects hand off: the brief carries the accepted option, resolved questions, and remaining steps. It does not only summarize the job and drop the rules.

## How it behaves

- **Mechanics are autonomous.** It does not ask permission to edit a file or run tests.
- **Direction is a question.** Ambiguous requirements and two-way design choices stop. The question is YES/NO with options.
- **Evals carry correctness, not model size.** Binary checks and the repo's tests decide pass/fail. A cheaper model can iterate until those checks pass.
- **It grows on this repo.** After a procedure is learned, it writes a skill that fires the next time. Notes are not skills.
- **You use the subscription you already pay for.** An API key is fallback. See [subscription-auth.md](docs/subscription-auth.md).

Independent review is required. A **different vendor** is recommended when two are configured (different training data, less agreeableness). Most people have one provider. A second pass in a **fresh session** on that provider still counts. The writer must not review its own conversation.

## How we know

Two layers. Both are required. Passing only one is not success.

- **A. Workplace** — real Tasks and Projects, first on [convo-agent](https://github.com/alemtani/convo-agent). First-pass merge-ready, zero mechanical questions, corrective PRs after merge, cost.
- **B. Public comparison** — same published protocol as the row we cite, plus a same-model baseline scaffold. Headline: Senior SWE-Bench via Harbor. The card is void without that control row.

Scorecards, sources, and what we will not treat as a goal live in [docs/success-criteria.md](docs/success-criteria.md). That file is the weekly object. This file does not duplicate it.

## What we keep from v1

Handoff instead of compaction, ask on direction, verify before "done" — these stay as **mechanisms**. They are not the product. The product is the teammate loop above.

## Non-goals

- Not an IDE.
- Not cloud-mandatory. Local-first. Optional isolation later.
- Not zero questions. Fewer, better, directional.
- Not a 1M-window or 1K-subagent arms race.
- Not user-maintained memory files.
- Not "done" because a nonempty diff exists.

## Where we are

The engine is real: ReAct loop, architect/editor, library, handoff, checkpoints, providers, eval harnesses. The cockpit has shipped more than v1 admitted (diffs, slash commands, streaming, `/context`, `/cost`).

The gap that blocks use: subscription sign-in. Kadmon still asks for a console API key on top of SuperGrok (and the same pattern for other vendors). That is first. Then the Task/Project loop against the scorecards.
