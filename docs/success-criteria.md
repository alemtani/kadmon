# Kadmon — How we know it is good

Status: working spec, 2026-08-20.
Sign-in / subscriptions: [`subscription-auth.md`](subscription-auth.md) (separate doc, separate context).

This is the weekly score object. Each criterion names a **why** and a **source**. The source is the reason the line exists. It is not a claim that Kadmon already meets it.

---

## Product

Kadmon is a teammate coding agent. You give it a Task or a Project. A Task comes back as a pull request that already passed the repo's tests and an independent review. A Project stops for a design YES/NO, then those PRs. It asks only when direction is unclear. It writes skills that fire the next time. Cheap models do the work. Evals carry correctness.

---

## Two layers

Internal gates can be arbitrary. An agent can pass them and still lose on a public protocol, and still ship bugs after merge. Two independent layers. Passing only one is not success.

| Layer | Question | Failure if used alone |
|---|---|---|
| **A. Workplace** | Does it finish real work with almost no babysitting? | Easy gates on a repo we wrote. In-distribution only. |
| **B. Public comparison** | Is the same system competitive on a **published** protocol? | Saturated or gameable leaderboard. Can take a test, cannot ship a PR. |

A third check sits **after** merge: defects that come back. Pre-merge gates cannot see this. This is DORA change-fail rate, applied to agent-merged work ([16]).

No 1–5 quality scores. No live conversation-watcher LLM. Binary pass/fail and code assertions first ([1], [2]). LLM-as-judge only when a mechanical check cannot exist, and then still binary ([1]).

---

## Comparison card

Numbers without a date, harness, model, and **same-model baseline row** are not reportable. Comparing `Kadmon+Grok` to a SOTA row run on a different model confounds scaffold and model. Terminal-Bench analysis finds model choice usually moves the score more than the agent scaffold ([10]). The control row is what makes the number about *Kadmon*.

```
Kadmon <version>   <date>   harness <id>

Layer A — workplace
  (not a general capability claim until ≥2 repos, one not authored here)
  first-pass merge-ready     k/N   (Wilson 95% CI)
  mechanical questions       0/N
  corrective PRs ≤14 days    k/N   (Wilson 95% CI)
  median human minutes       M
  $ per Task                 $x

Layer B — public (void unless the same-model baseline row is present)
  Senior SWE-Bench tasteful-solve
    Kadmon + <model>                 xx%
    Terminus 2 + <same model>        yy%     ← required control
    cited leaderboard row            zz%     (agent, model, date named)
  $ / instance                       $a / $b / $c
  Terminal-Bench 2.x (secondary only; same three-row shape)
```

Tied means Wilson (or the bench's published) intervals overlap ([14]). We do not say "better" inside overlapping error.

Wilson, not Wald: Wald intervals collapse at 0/n or n/n and under-cover at small n. Brown, Cai, and DasGupta recommend Wilson for binomial proportions ([14]). At n≈10, 8/10 has a Wilson 95% interval of roughly 49–96%. A bare 80% overstates precision.

---

## Layer A — Workplace

First dogfood repo: [convo-agent](https://github.com/alemtani/convo-agent). Kadmon is the agent under test.

Until a **second repo not authored here** has run Tasks, Layer A is in-distribution only. Do not pool repos. Do not present it as a general capability number. SWE-bench Pro's private split is harder than public for this reason: unseen codebases drop resolve rate ([18]).

### Class rule

Default is **Task**. It becomes a **Project** if any tripwire is YES:

1. User labeled it project / RFC / design.
2. **Mechanical (script, not the agent's opinion):** the diff adds a public-API path, a provider, a datastore migration, or a new production secret name.
3. It cannot ship as one PR (two independently shippable surfaces, or two PRs already listed).
4. `AGENTS.md` or a skill in that repo marks the area as design-first.

If a mechanical tripwire fires and the agent still classed Task, T1 is NO. The agent does not self-certify class. Self-labels are the same failure mode as an unvalidated LLM-as-judge ([1]).

On convo-agent: A1 / C0 / Phase 6 are Tasks. Phase 7 (durable DB) and V2 (converser/grader split) are Projects.

### Task scorecard

| ID | YES | NO (the cheat) | Why this line exists |
|---|---|---|---|
| **T1 Class** | Tripwires match the label (script + user label) | Skipped a tripwire, or a design for a one-PR fix | Class is a gate, not a vibe. Mechanical tripwires remove self-grading ([1]). |
| **T2 Tests** | Default gate green **and** test count on head ≥ base **and** no new skip/xfail vs base **and** (if bugfix) a test that fails on base and passes on head | “Green” because tests were deleted or skipped | SWE-bench resolved = FAIL_TO_PASS now pass **and** PASS_TO_PASS still pass ([4], [5]). A patch that deletes the failing test is not a fix. Kadmon's current harness marks resolved if a nonempty diff exists; that number is not used. |
| **T3 PR** | A GitHub PR exists with the diff | Diff only in the working tree | The workplace unit of delivery is a reviewable change, not a local patch. Matches how SWE-bench and Senior SWE-Bench score work ([4], [9]). |
| **T4 Review** | Independent review in a **fresh session** (no writer history). Request-changes fixed or waived in writing. **Recommended:** a different vendor when two are configured. **Acceptable:** a second pass of the same provider when that is all the user has | Writer reviewing its own conversation; or no review at all | Same-session self-review has agreeableness bias ([12]). Multi-Review: extra passes help even on one model (Self-Agg); Multi-Agg (different LLMs) is a further lever, not a gate ([11]). Most developers have one provider. Different vendor is recommended, not required. Seeded-defect catch rate is a periodic calibration when we run it, not a per-PR fail ([15]). |
| **T5 Interrupts** | Zero questions from the mechanical list (permission to edit, run tests, install a dep). Directional questions allowed: YES/NO with options, and the answer changes the shipped interface | Permission nags, or silence that L1 later catches | Mechanical interrupts are not the product. Silence is also a cheat: the agent guesses. L1 is the lagging check that makes T5 honest ([16]). |
| **T6 Rounds** | Approve on round 1, or ≤2 rounds, **independent of size** | Round 3+. A large diff that cannot pass in 2 rounds should have been a Project or a split (T1) | Actor–critic review literature treats 3–5 rounds as a practical cap, with 1–2 for automated gates ([11] discussion in industry surveys). Size-gating extra rounds is gameable (pad past a line cap, or split to dodge review). |
| **T$ Cost** | Always reported next to Layer B $ / instance | Hidden, or graded against a cap we set ourselves | Senior SWE-Bench already publishes $ / task beside tasteful-solve (Grok 4.5 ~$1 vs a frontier row ~$29 at higher solve rate) ([9]). A self-set cap is not a comparison. |

First-pass merge-ready = `T2 ∧ T3 ∧ T4 ∧ T5 ∧ T6`.

Human merge is a human YES/NO. On convo-agent, merge to `main` deploys. A separate deploy gate exists only when the Task is "change prod config"; then `/health` must report `auth=enabled`.

### Project scorecard

| ID | YES | NO | Why this line exists |
|---|---|---|---|
| **P1 Class** | A tripwire fired (script or user) | Jumped to code on Phase-7-shaped work | Same as T1. Senior SWE-Bench splits *investigate and fix* vs *design and build* for this reason ([9]). |
| **P2 Design file** | Repo file: problem, options, recommendation, open questions, test plan | Chat-only plan | The design is the artifact an independent reviewer and a human can accept or reject. Chat is not recoverable context ([6], [7]). |
| **P3 Design review** | Human YES/NO **after** an independent written review (fresh session; different vendor recommended, not required) | Implementation started before YES | Design is where extrapolation is highest, so the reviewer must not share the writer's session ([12]). One provider is enough if the session is new. |
| **P4 Children** | Each implementation PR is a Task and passes T2–T6 | One grab-bag PR | Large diffs overwhelm review. Industry review data: returns drop sharply above ~500 lines; chunking is a prerequisite ([11] / BugBot writeups [13]). |
| **P5 Spec still true** | Every P2 open question has a committed resolution **and** every interface named in the design is grep-able in the shipped code | Agent says “matches” | Binary, greppable. Not an LLM “does the spec match.” |
| **P6 Handoff integrity** | If the Project crosses a context reset, the brief contains: accepted option from P3, every resolved question + answer, remaining plan steps. Parsed fields, not prose similarity | Reset with a summary that keeps the *task* and drops the *rules* | Long context is unreliable in the middle (Liu et al., U-shaped use of the window) ([6]). Compaction is worse for constraints: *Lost in Compaction* finds current compactors keep about **17% of session rules** on average while still remembering the job ([7]). A Project will hand off. The brief must carry decisions, not just “continue the feature.” |
| **P7 No re-ask** | After handoff, the log does not contain a directional question whose answer is already in the brief | Agent re-asks a resolved design question | Decision retention is the measurable form of “it did not forget.” If P6 fields are present and P7 still fails, the brief is not in the model's usable context ([6]). |
| **P8 Handoff, not silent drop** | When utilization crosses the configured threshold, the run writes a brief and resets. It does not only pop middle messages | Context “managed” by deleting turns with no brief | Bigger windows delay degradation; they do not remove lost-in-the-middle ([6]). METR's result on long software tasks: the bottleneck is completing the horizon, not one local edit ([8]). Kadmon's stated strategy is write-brief → reset → continue. A Project that only truncates has abandoned that strategy. |

P6–P8 are the Project-specific addition. Tasks are usually one context. Projects are not.

### Growth (next similar item only)

| ID | YES | Why this line exists |
|---|---|---|
| **G1 Wrote** | New or updated `SKILL.md` (not a diary in `decisions.md`) | Anthropic's Agent Skills: a skill packages *how* to do a procedure. Session notes are *where we left off*. Those are different objects ([17]). |
| **G2 Fired** | Log shows that skill was loaded **and** its declared precondition matched | A file nobody loads is not learning. Measure use, not bytes on disk. |
| **G3 Delta** | Report tokens, rounds, questions vs the earlier run. **No “helped” verdict on n=1.** A skill may pre-register one metric; “helped” then requires the drop to beat run-to-run variance (same Task type run twice) | One of three metrics will often move down by chance. Causal claims need a pre-registered outcome and a variance baseline. If we cannot measure variance, stop at G2. |

### Lagging practice — L1

Of the last N merged Tasks, how many needed a corrective PR within 14 days. Wilson 95% CI. Lives in the weekly headline.

This is DORA **change fail rate**: the share of changes that need a hotfix, rollback, or fix-forward after they ship ([16]). Every other gate fires at merge. Without L1, T2–T6 can all be YES and the work still comes back. T5 (silence) is honest only because L1 exists: if the agent guesses instead of asking, L1 moves.

In-repo warning: convo-agent already ran this pattern. The `coherence` tag ran on every turn and, in `evals/coherence/`, tagged a gaming turn `on_track` every time. A watcher LLM is not L1.

---

## Layer B — Public comparison

**Headline bench:** Senior SWE-Bench, via Harbor, always with a same-model baseline scaffold row. Underspecified prompts, long horizon, tasteful-solve. Published SOTA was about 29% in July 2026 — on a *different* model, which is why that number is never the only row ([9]).

**Secondary only:** Terminal-Bench 2.x, same three-row shape ([10]). Never the headline. Proves we are not fitting one bench.

**Not on the card**

- SWE-bench Verified as a headline. Frontier scores cluster in the mid-90s. OpenAI stopped treating it as a frontier eval ([5], [18]). An audit of “solved” cases found a large share semantically wrong; harnesses can be exploited to 100% with no issues actually solved.
- Aider Polyglot as capability. Exercism functions, not a sprint.
- METR unless we actually freeze and run a suite ([8]).
- Kadmon's current `resolved=bool(patch)` harness.

**Smoke only:** Kadmon's own pytest. Maybe five Polyglot exercises, to prove the loop still starts.

### Protocol (a missing row voids the card)

1. Same harness as the cited row (Harbor) ([10]).
2. Three rows: Kadmon+model, published baseline scaffold+**same** model, cited leaderboard row with its model named.
3. Same split the leaderboard uses. If the public split is dirty (SWE-bench Pro public was audited ~30% broken), use the split the authors recommend ([18]).
4. Isolation. No gold-PR lookup. Senior SWE-Bench documents benchmark awareness and reward hacking in newer models ([9]).
5. Cost and wall-clock per instance, all three rows ([9]).
6. Date, agent version, model version, harness version.
7. Tied = overlapping intervals ([14]).
8. We do not tune prompts on the split we report.

If A is strong and B is weak: a workflow on one repo. If B is strong and A is weak: can take a test, cannot ship. If L1 is high: both can look fine and the work still comes back. If P6–P8 fail: the Project looked fine in the first hour and forgot the design in the third.

---

## What we will not score as a goal

- SWE-bench Verified headline %
- Aider Polyglot as capability
- Live LLM-as-watcher (failed on convo-agent V0; compaction analog in [7])
- 1–5 taste scores ([1], [2])
- Library file count
- A dollar cap we set ourselves
- “Helped” on a single pair of Tasks

---

## References

Sources the criteria stand on. Read these if a line feels arbitrary.

1. Hamel Husain, *LLM Evals FAQ* — binary pass/fail over Likert 1–5; code assertions before LLM-as-judge. https://hamel.dev/blog/posts/evals-faq/
2. Arize, *LLM as a Judge* primer — binary verdicts more stable than fine numeric scales. https://arize.com/guides/llm-as-a-judge/
3. Lianmin Zheng et al., *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*, NeurIPS 2023 — position bias and why naive LLM judges are noisy. https://arxiv.org/abs/2306.05685
4. Carlos E. Jimenez et al., *SWE-bench: Can Language Models Resolve Real-world GitHub Issues?*, ICLR 2024 — resolved iff FAIL_TO_PASS pass and PASS_TO_PASS do not regress. https://arxiv.org/abs/2310.06770
5. OpenAI, *Introducing SWE-bench Verified* (2024), and later deprecation of Verified as a frontier headline (2026). https://openai.com/index/introducing-swe-bench-verified/
6. Nelson F. Liu et al., *Lost in the Middle: How Language Models Use Long Contexts*, TACL 2024 — U-shaped use of the window; middle of long context is unreliable. https://arxiv.org/abs/2307.03172
7. *Lost in Compaction: Evaluating Side-Constraint Loss under Context Compaction*, arXiv:2608.11242 — compactors kept ~17% of session **rules** on average while still remembering the task. https://arxiv.org/abs/2608.11242
8. METR, *Measuring AI Ability to Complete Long Software Tasks* / Time Horizon 1.1 — 50% and 80% horizons; long-horizon completion is the bottleneck. https://metr.org/time-horizons/ · https://arxiv.org/abs/2503.14499
9. Snorkel AI, *Senior SWE-Bench* (2026) — underspecified PM prompts, tasteful-solve (SOTA ~29% Jul 2026), $ / task, 6h cap, benchmark awareness. https://snorkel.ai/blog/senior-swe-bench-evaluating-coding-agents-like-senior-engineers/
10. Mike A. Merrill et al., *Terminal-Bench*, ICLR 2026 — Harbor protocol; published agent+model+date rows; model often moves the score more than scaffold. https://arxiv.org/abs/2601.11868
11. Zhengran Zeng et al., *SWR-Bench* / Multi-Review, arXiv:2509.01494 — Self-Agg vs Multi-Agg; F1 +43.67% at n=10 Self-Agg; plateau ~5–10 passes. https://arxiv.org/abs/2509.01494
12. *Mitigating Agreeableness Bias in LLM Judge Evaluations*, arXiv:2510.11822 — same-family judges fail to reject bad work. https://arxiv.org/abs/2510.11822
13. Cursor, *Building a better Bugbot* (2026) — parallel review passes, majority vote, resolution rate of flagged issues (vendor metric; use as design pattern, not as our number). https://cursor.com/blog/building-bugbot
14. E. B. Wilson (1927); Lawrence D. Brown, T. Tony Cai, Anirban DasGupta, *Interval Estimation for a Binomial Proportion*, Statistical Science 16(2), 2001 — Wilson score interval for small n. https://doi.org/10.1214/ss/1009213286
15. René Just et al., *Are Mutants a Valid Substitute for Real Faults in Software Testing?*, ICSE 2014; PIT; Petrović & Ivanković, mutation testing at Google (ICST 2018) — seed known defects to measure whether a suite (or a reviewer) catches them. https://homes.cs.washington.edu/~rjust/publ/mutants_real_faults_icse_2014.pdf
16. DORA, *Change fail rate* — share of changes that need hotfix / rollback / fix-forward after they ship. https://dora.dev/guides/dora-metrics/
17. Anthropic, *Agent Skills* — skills package how-to; they are not session memory. https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
18. Scale AI, SWE-bench Pro; SWE-Bench ProMax (arXiv:2608.09802); OpenAI audit that ~30% of Pro public tasks were broken — why Verified/public splits are not the headline. https://arxiv.org/html/2608.09802v1

In-repo: `convo-agent` `evals/coherence/` (V0) — a live watcher tag that never caught the gaming turn. Empirical reason we do not put a judge on the conversation.
