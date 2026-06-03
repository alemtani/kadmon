# Transparency UI: /context and /cost

## Problem

Kadmon's context budget and token spend are invisible to users. The agent manages context
autonomously (compaction at 0.9, handoff warning at 0.8), but users have no way to see how
much runway remains or how much a session has consumed. No competitor exposes this.

## Solution

Two slash commands surface existing backend accessors in the terminal.

### /context — Context Budget Meter

Reads `agent.context.stats()` → `ContextStats` and renders:

- A 30-char progress bar (green < 60%, yellow 60-79%, red ≥ 80%)
- Utilization percentage
- Used / max token counts (formatted with commas)
- Message count
- **⚠ warning** when `near_handoff` is True (≥ 80% utilization)

Renderer: `render_context_meter(stats, target_console)` in `cli_display.py` (~15 lines).

### /cost — Token Usage & Cost Estimate

Reads `agent.usage_summary()` → `UsageSummary` and renders:

- Input / output / total tokens (always shown, accurate from provider)
- Turn count
- **Dollar estimate** only if `[pricing]` section exists in `.kadmon/config.toml`:
  ```toml
  [pricing]
  input = 3.0    # $/1M input tokens
  output = 15.0  # $/1M output tokens
  ```
- If pricing absent: tokens shown + one-line hint about configuring pricing

No prices are hardcoded in source. Users opt into cost visibility by configuring their
model's pricing in config. This keeps the display honest and provider-agnostic.

Renderer: `render_cost_summary(usage, model, pricing, target_console)` in `cli_display.py`.

## Wiring

Both commands dispatch through `handle_slash_command()` → `SlashAction.CONTEXT` / `COST`.
The REPL in `cli.py` passes `agent.context.stats()` and `agent.usage_summary()` to the
renderers. Pricing is loaded once at REPL start from `.kadmon/config.toml` via `_load_pricing()`.

## Design Decisions

- **Tokens always, cost only if configured** — avoids stale/wrong hardcoded prices.
- **char/4 estimate** — `used_tokens` is approximate (existing heuristic). Honest labeling.
- **Separate from /status** — /context and /cost are quick glances, not session summaries.

## Why This Is the Wedge

No current AI coding agent shows users their context budget. This is the "transparent
context budgeting" differentiator made tangible — users can watch utilization climb, see
the handoff threshold approaching, and understand the cost of their session.

## Files

- `kadmon/cli_display.py` — `render_context_meter`, `render_cost_summary`, updated dispatch
- `kadmon/cli.py` — wiring in REPL, `_load_pricing()`
- `tests/test_transparency_ui.py` — rendering + dispatch tests
