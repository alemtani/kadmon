# Git Workflow Tool

## Problem

The agent could only produce patches via `submit` (a raw `git diff`). It had no way to
stage files, create commits, inspect history, or manage branches — forcing users to handle
all git workflow outside the agent. The `shell` tool could run arbitrary git commands but
with no safety guardrails against destructive operations.

## Solution

A dedicated `git` tool with a strict whitelist of safe, local-only actions:

| Action   | Description                                  |
|----------|----------------------------------------------|
| `status` | Short-format working tree status             |
| `diff`   | Unstaged diff (or `--cached` with `staged`)  |
| `log`    | Oneline log, configurable count (max 50)     |
| `branch` | List branches, or create one by `name`       |
| `add`    | Stage specific file paths                    |
| `commit` | Commit staged changes with a message         |

## Safety Boundary

Any action not in the whitelist returns an error without executing. Explicitly refused:

- **Remote operations**: push, pull, fetch — agent never touches the remote
- **Destructive rewrites**: reset, rebase, merge, clean
- **Force flags**: never uses `-f`, `--force`, `--hard`
- **Deletion**: branch -D, tag delete
- **Option injection via user values**: a `_reject_option_like` guard rejects any
  user-supplied string (branch name, path, paths) that starts with `-`. Additionally,
  all git invocations that accept a pathspec or refname use a `--` separator before
  user values, preventing them from being parsed as options even if the guard is
  somehow bypassed.

Rationale: the agent earns trust through local, reversible operations. Pushing and
force-rewriting are high-risk, irreversible, and belong to the human operator.

## Integration

Registered in `create_default_registry()` alongside other tools:

```python
from kadmon.tools.git_tool import GitTool
registry.register(GitTool(repo_root))
```

Uses the same `repo_root` / `subprocess` / `ToolResult` patterns as `ShellTool` and
`SubmitTool`. No new dependencies.

## Testing

`tests/test_git_tool.py` — 10 tests against a `tmp_path` scratch repo:
- Status shows untracked files
- Add + commit succeeds, log shows message
- Diff (unstaged and staged) works
- Branch create and list
- `add_all` flag stages tracked changes before commit
- Destructive/unknown actions (push, reset, etc.) return error without executing
- Missing required params (message, paths) return actionable errors

## Files Changed

- `kadmon/tools/git_tool.py` — new tool implementation
- `kadmon/tools/__init__.py` — import and registration
- `tests/test_git_tool.py` — test coverage
