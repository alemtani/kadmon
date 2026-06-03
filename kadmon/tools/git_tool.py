"""Safe, repo-scoped git operations for the agent."""

import subprocess
from pathlib import Path

from kadmon.tools.base import Tool, ToolResult

SAFE_ACTIONS = frozenset({'status', 'diff', 'log', 'branch', 'add', 'commit'})


def _reject_option_like(value: str, label: str) -> ToolResult | None:
    """Return an error ToolResult if value looks like a git option, else None."""
    if value.startswith('-'):
        return ToolResult(
            output=f"Refusing argument that looks like an option ({label}): {value!r}",
            error=True,
        )
    return None


class GitTool(Tool):
    """Run safe git operations within the repo. Destructive/remote actions are refused."""

    name = 'git'
    description = (
        'Run safe git operations: status, diff, log, branch, add, commit. '
        'Remote and destructive actions (push, pull, reset, rebase, clean, force) are refused.'
    )
    parameters = {
        'type': 'object',
        'properties': {
            'action': {
                'type': 'string',
                'enum': list(SAFE_ACTIONS),
                'description': 'Git action to perform.',
            },
            'message': {'type': 'string', 'description': 'Commit message (required for commit).'},
            'paths': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'File paths for add.',
            },
            'staged': {'type': 'boolean', 'description': 'Show staged diff (default false).'},
            'path': {'type': 'string', 'description': 'Limit diff to a specific path.'},
            'n': {'type': 'integer', 'description': 'Number of log entries (default 10).'},
            'name': {'type': 'string', 'description': 'Branch name to create.'},
            'add_all': {'type': 'boolean', 'description': 'Stage all tracked changes before commit.'},
        },
        'required': ['action'],
    }

    def __init__(self, repo_root: str):
        self._root = Path(repo_root).resolve()

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get('action', '')
        if action not in SAFE_ACTIONS:
            return ToolResult(
                output=f"Action '{action}' is disabled for safety. Allowed: {', '.join(sorted(SAFE_ACTIONS))}.",
                error=True,
            )
        handler = getattr(self, f'_do_{action}')
        return handler(kwargs)

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ['git', *args],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(self._root),
        )

    def _result(self, proc: subprocess.CompletedProcess[str]) -> ToolResult:
        output = (proc.stdout or proc.stderr).strip()
        if proc.returncode != 0:
            return ToolResult(output=output or 'git command failed', error=True)
        return ToolResult(output=output or '(no output)')

    def _do_status(self, kwargs: dict) -> ToolResult:
        return self._result(self._run(['status', '--short']))

    def _do_diff(self, kwargs: dict) -> ToolResult:
        args = ['diff']
        if kwargs.get('staged'):
            args.append('--cached')
        path = kwargs.get('path')
        if path:
            if err := _reject_option_like(path, 'path'):
                return err
            args.extend(['--', path])
        return self._result(self._run(args))

    def _do_log(self, kwargs: dict) -> ToolResult:
        try:
            n = int(kwargs.get('n', 10))
        except (TypeError, ValueError):
            return ToolResult(output="'n' must be an integer.", error=True)
        n = min(n, 50)
        return self._result(self._run(['log', '--oneline', f'-{n}']))

    def _do_branch(self, kwargs: dict) -> ToolResult:
        name = kwargs.get('name')
        if name:
            if err := _reject_option_like(name, 'name'):
                return err
            return self._result(self._run(['branch', '--', name]))
        return self._result(self._run(['branch']))

    def _do_add(self, kwargs: dict) -> ToolResult:
        paths = kwargs.get('paths')
        if not paths:
            return ToolResult(output="'paths' is required for add.", error=True)
        for p in paths:
            if err := _reject_option_like(p, 'paths'):
                return err
        return self._result(self._run(['add', '--', *paths]))

    def _do_commit(self, kwargs: dict) -> ToolResult:
        message = kwargs.get('message')
        if not message:
            return ToolResult(output="'message' is required for commit.", error=True)
        if kwargs.get('add_all'):
            self._run(['add', '-u'])
        return self._result(self._run(['commit', '-m', message]))
