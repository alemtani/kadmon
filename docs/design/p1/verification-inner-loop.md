# Verification Inner Loop

## Overview

**Problem:** `BacktrackManager` exists in `kadmon/agent/backtrack.py` with rollback logic, but nothing in the agent loop triggers rollback on verification failure. When tests fail after an edit, the agent only sees the error output and must figure out recovery on its own — often looping on the same broken approach.

**Goal:** Wire checkpoint-based rollback into the agent loop so that a failed verification step automatically restores files to their pre-edit state and retries with explicit feedback, bounded by a cap to prevent infinite loops.

## Integration Design

**Hook point:** `kadmon/agent/loop.py:_process_response`, after tool results are collected and before the existing loop-detection block.

**Flow:**

1. After tool execution, scan results for a `verify` tool call that returned `is_error: True`.
2. If found AND `_verify_retry_count < _verify_retry_max` AND a `CheckpointManager` is available:
   - Call `checkpoint_mgr.rollback()` to restore files to the latest checkpoint (created by `WriteFileTool`/`EditFileTool` before each edit).
   - Increment `_verify_retry_count`.
   - Inject a structured retry message with failure output, rolled-back file list, and remaining attempts.
   - Return `None` (loop continues — LLM sees the retry prompt and tries differently).
3. If cap exhausted or no checkpoint manager: fall through to existing behavior (loop detection, recovery prompt, handoff). No regression.
4. On successful verification: reset `_verify_retry_count = 0`.

**Parameters:**
- `checkpoint_manager: CheckpointManager | None` — passed to `AgentLoop.__init__`, optional.
- `verify_retry_max: int = 2` — default cap, configurable per-agent.

**Activation:** `create_default_registry()` exposes the edit tools' `CheckpointManager` on the
registry as `registry.checkpoint_manager`. `AgentLoop.__init__` falls back to it
(`checkpoint_manager or getattr(tools, "checkpoint_manager", None)`), so the inner loop activates
automatically — and rolls back the *same* checkpoints the edit tools create — without changing any
call-site signatures (cli, workers, eval all benefit).

## Why File-Based Checkpoints (not git stash)

The `BacktrackManager` references `kadmon/agent/checkpoint.py` (git-stash based), but the tools already create file-level checkpoints via `kadmon/checkpoints.py` before every edit. Using the file-based system means:
- Zero git dependency in tests
- Checkpoints are already being created (no new save calls needed)
- Rollback is fast and deterministic

## Trust Pillar Advancement

This directly implements the "verification-first trust" differentiator: the agent doesn't just *see* a test failure — it *undoes* the damage and tries again with a clean slate. This builds user confidence that autonomous edits won't accumulate broken state.

## Testing

`tests/test_backtrack_integration.py` covers:
- Verify failure triggers rollback + retry, then success on second attempt
- Retry cap honored: after N failures, falls through without rollback
- Successful verify resets retry counter
- No checkpoint manager → existing behavior preserved (no crash)

All tests use `FakeVerifyTool` (configurable fail count) and the real `CheckpointManager` against `tmp_path`.

## Future

- Wire `BacktrackManager.backtrack()` for plan-level backtracking (mark step failed, skip to alternative) — separate from this per-verification retry.
- Expose retry cap in `.kadmon/config.toml`.
