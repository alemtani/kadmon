# Context & Cost Transparency — Backend Accessors

## Problem

Kadmon has no user-facing visibility into context-window usage or token spend. Compaction
triggers silently at 0.9 utilization. Users cannot tell how close they are to a handoff, how
many tokens a session has consumed, or how much runway remains. This makes autonomous sessions
feel opaque and uncontrollable.

## Solution

Two read-only accessors expose the internal state the CLI track needs to render a context
meter (`/context`) and a cost display (`/cost`).

### ContextManager.stats() → ContextStats

Returns a frozen dataclass snapshot:

| Field | Type | Description |
|-------|------|-------------|
| `used_tokens` | int | Current char/4 estimate of context consumed |
| `max_tokens` | int | Budget ceiling (default 200 000) |
| `utilization` | float | 0.0–1.0 ratio |
| `message_count` | int | Messages in history |
| `near_handoff` | bool | True when utilization ≥ 0.8 |

Pure read — no side effects, no new estimation logic.

### AgentLoop.usage_summary() → UsageSummary

Returns a frozen dataclass of cumulative session totals:

| Field | Type | Description |
|-------|------|-------------|
| `input_tokens` | int | Sum of all input tokens reported by provider |
| `output_tokens` | int | Sum of all output tokens reported by provider |
| `total_tokens` | int | input + output |
| `turns` | int | Number of model calls completed |

Accumulation happens in `_accumulate_usage()`, called from `_call_llm()` after **both** the
streaming path (on `StreamChunk.DONE`) and the non-streaming `complete()` path.

## Design Decisions

**0.8 near-handoff threshold.** The handoff monitor triggers context reset when quality
degrades — empirically correlated with ≥80% utilization. Exposing this as `near_handoff`
lets the CLI warn users before the autonomous handoff fires. Compaction itself triggers at
0.9 — the 0.8 flag is an early warning, not a trigger.

**Tokens only, no dollar cost.** Pricing varies by provider and model. The CLI track owns a
config-driven pricing table; this backend just provides accurate token counts as input.

**char/4 estimate caveat.** The `used_tokens` field uses the existing character-count ÷ 4
heuristic. It's fast and zero-dependency but imprecise (especially for non-English or
structured content). A real tokenizer (tiktoken or provider-specific) is future work — the
accessor shape won't change when that lands.

## Testing

`tests/test_transparency.py` covers:
- `stats()` on empty and populated context managers
- `near_handoff` flipping at the 0.8 boundary
- `usage_summary()` accumulation across multiple turns (non-streaming)
- `usage_summary()` via the streaming path with a fake `provider.stream()`
- Initial zero state before any model calls

## Files Changed

- `kadmon/agent/context.py` — added `ContextStats` dataclass, `stats()` method
- `kadmon/agent/loop.py` — added `UsageSummary` dataclass, `_accumulate_usage()`,
  `usage_summary()`, token counters in `__init__`
- `tests/test_transparency.py` — new (8 tests)
- `docs/design/p1/context-cost-transparency.md` — this file
