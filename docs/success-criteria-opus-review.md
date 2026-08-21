**Layer B is still not comparable as published.** The protocol section says the right thing (same-model baseline agent, same harness, same date), but the recruiter one-pager throws it away. The card puts "Kadmon+Grok 17%" next to "published SOTA 29.1%" — and that SOTA row is a different model (the draft itself names the Grok 4.5 vs Fable 5 spread). That single comparison confounds scaffold and model, which is the exact thing protocol step 1 forbids. A recruiter reading the one-pager cannot tell whether Kadmon is behind because of Grok or because of Kadmon. Until the same-model baseline row (Terminus 2 / mini-SWE-agent on the same model and date) appears **in the published card, not just the protocol**, Layer B is a screenshot, not a comparison. That is the first fix.

Now the findings, worst first.

---

## Blockers

**B-1 · Layer B one-pager · confounded comparison.** The card compares Kadmon+Grok to a SOTA number produced by another model. A dishonest agent (or a kind scorer) reports the flattering gap and never runs the control. **Replacement:** the card must carry three rows per bench, same date/harness: `Kadmon+<model>`, `<baseline scaffold>+<same model>`, and the cited leaderboard row (with its model named). No baseline-on-same-model row → the bench is not reportable that week. This is binary: the row is present or the card is void.

**B-2 · T2 · "green" hides gutted tests.** `pytest -q` green says nothing about whether the agent deleted, skipped, or `xfail`ed the test that was failing, or dropped coverage. This is the most gameable line in the whole doc, and it is the correctness gate. **Replacement, all binary:**
- Test count from `pytest --collect-only` on head ≥ base.
- No test newly marked `skip`/`xfail` vs base.
- For any bugfix Task: a test exists that fails on base and passes on head (regression test present).
Any NO → T2 NO. Without these, "tests green" is self-certified.

**B-3 · T4 + T6 conflict · rewards a toothless reviewer.** T4 only checks that a second-vendor review *artifact exists*. T6 rewards passing in *one round*. Together they pay the agent to use a weak reviewer that says "LGTM" fast. A kind reviewer is the failure mode, and the scorecard rewards it. **Replacement:** add reviewer calibration by seeded defects (mutation/bug-seeding is a published protocol). Periodically inject a known bug into a PR; if the reviewer's catch rate is below a pre-set floor, its reviews do not count toward T4. Also: T4 = every request-changes item is either fixed (commit) or waived with a written reason in the thread — not merely "a comment exists."

**B-4 · Growth G3 · unfalsifiable causal claim on n=1.** "T6 still YES, and tokens *or* rounds *or* questions dropped vs the earlier similar Task." Three metrics joined by OR, on two Tasks that are never identical, with no variance baseline. Noise alone lands one of three metrics lower most of the time, and the agent picks whichever dropped. This scorecard will almost always read YES and prove nothing. **Replacement:** the skill declares *one* metric it should reduce (pre-registered). "Helped" requires the drop on that one metric to exceed run-to-run variance, and you measure variance by running the earlier Task type twice. If you cannot measure variance, drop the causal claim: G3 = skill loaded AND its declared precondition matched (binary), report the delta with no "helped" verdict. n=1 cannot support causation; stop pretending it does.

---

## Majors

**M-1 · T1 · agent self-certifies its own class.** The agent does the work and then judges whether a tripwire fired. It can under-read its own diff ("no new public interface") to keep a Project labeled Task and skip design review. **Replacement:** compute the mechanical tripwires from the diff, not from judgment — new files under the public-API/providers path, new secret names in the config schema, new datastore migration files. If any fire and class was Task, T1 = NO automatically. Keep the human/label tripwires as-is; make the structural ones a script.

**M-2 · T5 · zero-questions rewards wrong guesses, and the split is self-labeled.** "Zero mechanical questions" plus agent-labeled mechanical-vs-directional means the agent both suppresses needed questions (guesses, ships wrong) and relabels any question it did ask as "directional." The metric rewards silence. **Replacement:** (a) enumerate mechanical (permission to run tests / install a dep / write a file) vs directional (answer changes the shipped interface) — no per-task judgment. (b) Add the counter-metric that makes silence honest: post-merge corrective-PR rate (see M-3). A suppressed question surfaces as rework; without a lagging metric, T5 pays for guessing.

**M-3 · Whole doc · everything is measured at merge time; nothing measures "in practice."** "Sucks in practice" = defects found *after* merge. Every gate (T2–T6) fires at or before merge, so an agent can look perfect and still ship bugs. This is open question 5, and it is a real hole. **Replacement — one binary lagging metric:** of the last N merged Tasks, how many needed a corrective PR within M days. Put it in the weekly headline. This is the honest practice-usage number; the current headline has none.

**M-4 · Layer A headline · point estimate on n≈10.** "8/10 first-pass" from ten Tasks has a Wilson 95% interval of roughly 49–96%. Reporting 80% to a recruiter implies a precision you do not have; 6/10 and 8/10 are statistically the same. **Replacement:** report the Wilson interval, not the bare fraction, and reuse that interval as the Layer B "tied" test (overlapping intervals = tied) so both layers use one published method instead of the undefined "published error bar" in protocol step 6 (many benches publish none).

**M-5 · Layer A · one repo, same author.** convo-agent is a single repo built by the Kadmon author. Passing it is "good on homework" by construction — the exact risk the two-layer design claims to guard against. **Replacement:** the workplace headline is not quotable to a recruiter until ≥1 second repo, not authored by the Kadmon team, has run Tasks; until then report per-repo, never pooled.

**M-6 · U1 · "without creating a console API key" lets a cached key through.** A pre-existing key in env satisfies "did not create." **Replacement:** U1 = with no API key present in env or config at all, the Task completes on subscription/CLI credentials only. Binary and unfakeable. And add the audit for the Claude path: Kadmon never reads an `sk-ant-oat*` token into its own HTTP client (grep the code path).

---

## Minors

**m-1 · Table naming · both layers labeled "A."** The two-numbers table lists "A. Workplace" and "A. Public comparison"; the body calls them Layer A and Layer B. Fix to A/B so the recruiter card and the scorecard reference the same names.

**m-2 · Headline conjunction drops T1 and T5.** "First-pass merge-ready = T2∧T3∧T4∧T6" excludes classification and interrupts, so an agent that misclassifies and interrupts mechanically still headlines well. Add T5 to the conjunction; T5 (no mechanical babysitting) is the core product claim.

**m-3 · T7 optional and self-set.** An optional cap the same team sets is not a criterion. **Replacement:** always report actual $ per Task (comparability comes from reporting next to the Layer B cost column, not from a self-chosen cap).

**m-4 · METR row "if we can run it."** Aspirational rows are not criteria. Either run it as a frozen binary suite with a stated horizon, or cut it from the card. Do not publish a maybe.

**m-5 · P5 · agent certifies its own "spec matches code."** **Replacement:** P5 = every open question in the P2 design has a committed resolution, and every interface named in the design is grep-able in the shipped code. Binary, not "matches."

---

## The five open questions

**Q1 — bench set, or one Harbor bench deep? → Go deep on one, plus one control; kill breadth.** Make Senior SWE-Bench the single headline (it matches the product: underspecified, PR-shaped, tasteful-solve), invoked through Harbor, always with a same-model baseline scaffold row. Keep Terminal-Bench only as a secondary "generalizes past one bench" smoke, never headline. **Why breadth fails:** four benches, each needing a date-freeze, a same-model control, cost, and a CI, cannot be re-run per Kadmon version. You will ship stale or control-less cards — which breaks the date-freeze and baseline requirements that are the *only* thing making Layer B comparable. One reproducible controlled number beats four uncontrolled ones.

**Q2 — T4 different-vendor too strict? → Correctly strict, but not sufficient.** Keep different-vendor. **Why "second sample of the same model is fine (Self-Agg)" fails:** Self-Aggregation raises answer quality by pooling samples; it does not make a model an adversarial critic of its own family's failures. Same-family review has correlated blind spots and agreeableness bias — it approves the mistakes it would make. But different-vendor alone still passes a kind reviewer (see B-3), so pair it with seeded-defect calibration. Different vendor = necessary; calibration = the sufficiency you're missing.

**Q3 — U1 fair for Claude; does subprocessing the CLI fail "Kadmon is the agent"? → Fair, and it does not fail the spirit.** Kadmon stays the agent: it classifies, plans, routes, and decides. The official `claude` CLI is a model-access transport, the same role an API endpoint plays — "who makes the HTTP call" was never the definition of the agent. **Why the alternative fails:** requiring native claude.ai OAuth makes U1 permanently unsatisfiable, because that OAuth does not exist for third parties (banned since Jan 2026). You would be scoring against reality for the vendor the user most wants as reviewer. Keep the guardrails already in the draft (local single-user, no token relayed to a server) and add the M-6 audit.

**Q4 — 500-line/3-round cap, or round cap independent of size? → Independent of size.** Fix the cap in rounds only (first-pass = approve on round 1; acceptable = ≤2 rounds), for any size. Handle size through the Class rule: a >500-line diff that cannot pass in ≤2 rounds is evidence it should have been a Project or split. **Why size-gating rounds fails:** it is gameable both directions — pad past 500 to buy extra rounds, or split to stay under and dodge the deeper review a big change needs — and it couples two independent things, so a NO is ambiguous (was it size or iterations?). Independent caps keep each line binary.

**Q5 — still a hole where Kadmon looks good internally and sucks in practice? → Yes, several, all above.** The biggest: no post-merge metric (M-3) — every gate fires at merge, so bugs found after merge are invisible. Add corrective-PR-within-M-days as a binary lagging headline number. Secondary holes: single same-author repo (M-5), toothless reviewer (B-3), gutted tests (B-2), and zero-questions rewarding wrong guesses (M-2). Fix M-3 first; it is the one number that catches all four when they slip through.

---

Want me to save this as `docs/success-criteria-opus-review.md`? I see a file by that name already untracked in the tree, so I did not overwrite it without asking.
