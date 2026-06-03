"""Tests for GitTool against a temporary git repository."""

import subprocess
from pathlib import Path

from kadmon.tools.git_tool import GitTool


def _init_repo(tmp_path: Path) -> Path:
    """Create a git repo with local user config."""
    subprocess.run(['git', 'init'], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=str(tmp_path), capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=str(tmp_path), capture_output=True)
    return tmp_path


def test_status_untracked(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / 'hello.txt').write_text('hi')
    tool = GitTool(str(repo))
    result = tool.execute(action='status')
    assert not result.error
    assert '?? hello.txt' in result.output


def test_add_and_commit(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / 'a.txt').write_text('content')
    tool = GitTool(str(repo))
    result = tool.execute(action='add', paths=['a.txt'])
    assert not result.error
    result = tool.execute(action='commit', message='initial commit')
    assert not result.error
    assert 'initial commit' in result.output


def test_log(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / 'a.txt').write_text('x')
    tool = GitTool(str(repo))
    tool.execute(action='add', paths=['a.txt'])
    tool.execute(action='commit', message='first')
    result = tool.execute(action='log')
    assert not result.error
    assert 'first' in result.output


def test_diff(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / 'a.txt').write_text('v1')
    tool = GitTool(str(repo))
    tool.execute(action='add', paths=['a.txt'])
    tool.execute(action='commit', message='init')
    (repo / 'a.txt').write_text('v2')
    result = tool.execute(action='diff')
    assert not result.error
    assert 'v2' in result.output


def test_diff_staged(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / 'a.txt').write_text('v1')
    tool = GitTool(str(repo))
    tool.execute(action='add', paths=['a.txt'])
    tool.execute(action='commit', message='init')
    (repo / 'a.txt').write_text('v2')
    tool.execute(action='add', paths=['a.txt'])
    result = tool.execute(action='diff', staged=True)
    assert not result.error
    assert 'v2' in result.output


def test_branch_create_and_list(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / 'a.txt').write_text('x')
    tool = GitTool(str(repo))
    tool.execute(action='add', paths=['a.txt'])
    tool.execute(action='commit', message='init')
    result = tool.execute(action='branch', name='feature-x')
    assert not result.error
    result = tool.execute(action='branch')
    assert not result.error
    assert 'feature-x' in result.output


def test_commit_add_all(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / 'a.txt').write_text('v1')
    tool = GitTool(str(repo))
    tool.execute(action='add', paths=['a.txt'])
    tool.execute(action='commit', message='init')
    (repo / 'a.txt').write_text('v2')
    result = tool.execute(action='commit', message='update', add_all=True)
    assert not result.error
    assert 'update' in result.output


def test_destructive_action_refused(tmp_path: Path, monkeypatch):
    repo = _init_repo(tmp_path)
    tool = GitTool(str(repo))
    called = []
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: called.append(a))
    for action in ['push', 'pull', 'reset', 'rebase', 'clean', 'fetch', 'merge']:
        result = tool.execute(action=action)
        assert result.error
        assert 'disabled for safety' in result.output
    assert called == [], "subprocess.run should not be called for refused actions"


def test_commit_requires_message(tmp_path: Path):
    repo = _init_repo(tmp_path)
    tool = GitTool(str(repo))
    result = tool.execute(action='commit')
    assert result.error
    assert "'message' is required" in result.output


def test_add_requires_paths(tmp_path: Path):
    repo = _init_repo(tmp_path)
    tool = GitTool(str(repo))
    result = tool.execute(action='add')
    assert result.error
    assert "'paths' is required" in result.output


def test_option_injection_branch(tmp_path: Path, monkeypatch):
    """Branch name starting with '-' is refused before subprocess runs."""
    repo = _init_repo(tmp_path)
    (repo / 'a.txt').write_text('x')
    tool = GitTool(str(repo))
    tool.execute(action='add', paths=['a.txt'])
    tool.execute(action='commit', message='init')

    called = []
    original_run = subprocess.run
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: called.append(a))

    for bad_name in ['-D', '--delete main', '-m evil']:
        result = tool.execute(action='branch', name=bad_name)
        assert result.error
        assert 'Refusing argument that looks like an option' in result.output
    assert called == []

    # Restore and confirm branches are intact
    monkeypatch.setattr(subprocess, 'run', original_run)
    result = tool.execute(action='branch')
    assert not result.error


def test_option_injection_paths(tmp_path: Path, monkeypatch):
    """Paths starting with '-' are refused for add and diff."""
    repo = _init_repo(tmp_path)
    tool = GitTool(str(repo))

    called = []
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: called.append(a))

    result = tool.execute(action='add', paths=['--force'])
    assert result.error
    assert 'Refusing argument' in result.output

    result = tool.execute(action='diff', path='--cached')
    assert result.error
    assert 'Refusing argument' in result.output

    assert called == []


def test_log_invalid_n(tmp_path: Path):
    """Non-integer n returns actionable error."""
    repo = _init_repo(tmp_path)
    tool = GitTool(str(repo))
    result = tool.execute(action='log', n='abc')
    assert result.error
    assert "'n' must be an integer" in result.output
