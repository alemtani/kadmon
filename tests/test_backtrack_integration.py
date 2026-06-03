"""Tests for verification-first inner loop: rollback + retry on verify failure."""

from unittest.mock import MagicMock

from kadmon.agent.loop import AgentLoop
from kadmon.checkpoints import CheckpointManager
from kadmon.providers.base import LLMResponse, ToolCall
from kadmon.tools.base import Tool, ToolRegistry, ToolResult


class FakeVerifyTool(Tool):
    """Verify tool that fails N times then passes."""

    name = "verify"
    description = "verify"
    parameters = {"type": "object", "properties": {"scope": {"type": "string"}}, "required": ["scope"]}

    def __init__(self, fail_count: int = 1):
        self._fail_count = fail_count
        self._calls = 0

    def execute(self, **kwargs) -> ToolResult:
        self._calls += 1
        if self._calls <= self._fail_count:
            return ToolResult(output="✗ FAILED (0.1s)\nAssertionError: expected 1 got 2", error=True)
        return ToolResult(output="✓ PASSED (0.1s)")


class FakeSubmitTool(Tool):
    name = "submit"
    description = "submit"
    parameters = {"type": "object", "properties": {}, "required": []}

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(output="diff --git a/f.txt")


def _make_agent(tmp_path, verify_tool: FakeVerifyTool, responses: list[LLMResponse]) -> AgentLoop:
    """Create AgentLoop with a fake provider and checkpoint manager."""
    provider = MagicMock()
    provider.complete.side_effect = responses

    registry = ToolRegistry()
    registry.register(verify_tool)
    registry.register(FakeSubmitTool())

    checkpoint_mgr = CheckpointManager(str(tmp_path))

    agent = AgentLoop(
        provider=provider,
        tools=registry,
        max_iterations=10,
        use_planning=False,
        checkpoint_manager=checkpoint_mgr,
    )
    return agent


def test_verify_failure_triggers_rollback_and_retry(tmp_path):
    """First verify fails -> rollback -> retry -> second verify passes -> submit."""
    # Create a file and checkpoint it (simulating a prior edit)
    (tmp_path / "a.py").write_text("original")
    checkpoint_mgr = CheckpointManager(str(tmp_path))
    checkpoint_mgr.create(["a.py"], tool="edit_file")
    # Simulate the edit that broke things
    (tmp_path / "a.py").write_text("broken edit")

    verify_tool = FakeVerifyTool(fail_count=1)

    responses = [
        # 1st iteration: agent calls verify, it fails
        LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="verify", arguments={"scope": "targeted"})]),
        # 2nd iteration: after rollback+retry message, agent calls verify again, passes
        LLMResponse(content="", tool_calls=[ToolCall(id="t2", name="verify", arguments={"scope": "targeted"})]),
        # 3rd iteration: agent submits
        LLMResponse(content="", tool_calls=[ToolCall(id="t3", name="submit", arguments={})]),
    ]

    provider = MagicMock()
    provider.complete.side_effect = responses

    registry = ToolRegistry()
    registry.register(verify_tool)
    registry.register(FakeSubmitTool())

    agent = AgentLoop(
        provider=provider,
        tools=registry,
        max_iterations=10,
        use_planning=False,
        checkpoint_manager=checkpoint_mgr,
    )
    result = agent.run("fix bug")

    # Verify submit succeeded
    assert "diff --git" in result
    # File was rolled back to checkpoint
    assert (tmp_path / "a.py").read_text() == "original"
    # Verify tool was called twice (fail then pass)
    assert verify_tool._calls == 2


def test_verify_retry_cap_honored(tmp_path):
    """Verify fails more times than retry cap -> falls through to normal behavior."""
    (tmp_path / "a.py").write_text("original")
    checkpoint_mgr = CheckpointManager(str(tmp_path))
    checkpoint_mgr.create(["a.py"], tool="edit_file")
    (tmp_path / "a.py").write_text("broken")

    # Always fails
    verify_tool = FakeVerifyTool(fail_count=99)

    responses = [
        # 1st verify: fails, retry 1
        LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="verify", arguments={"scope": "full"})]),
        # 2nd verify: fails, retry 2 (cap reached)
        LLMResponse(content="", tool_calls=[ToolCall(id="t2", name="verify", arguments={"scope": "full"})]),
        # 3rd verify: fails, but cap exhausted — no rollback, loop continues normally
        LLMResponse(content="", tool_calls=[ToolCall(id="t3", name="verify", arguments={"scope": "full"})]),
        # Agent gives up and submits
        LLMResponse(content="", tool_calls=[ToolCall(id="t4", name="submit", arguments={})]),
    ]

    provider = MagicMock()
    provider.complete.side_effect = responses

    registry = ToolRegistry()
    registry.register(verify_tool)
    registry.register(FakeSubmitTool())

    agent = AgentLoop(
        provider=provider,
        tools=registry,
        max_iterations=10,
        use_planning=False,
        checkpoint_manager=checkpoint_mgr,
        verify_retry_max=2,
    )
    result = agent.run("fix bug")

    assert "diff --git" in result
    # Retries were capped at 2
    assert agent._verify_retry_count == 2
    # Verify was called 3 times (2 retries + 1 after cap exhausted)
    assert verify_tool._calls == 3


def test_verify_success_resets_retry_count(tmp_path):
    """Successful verification resets the retry counter."""
    verify_tool = FakeVerifyTool(fail_count=0)  # Always passes

    responses = [
        LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="verify", arguments={"scope": "full"})]),
        LLMResponse(content="", tool_calls=[ToolCall(id="t2", name="submit", arguments={})]),
    ]

    provider = MagicMock()
    provider.complete.side_effect = responses

    registry = ToolRegistry()
    registry.register(verify_tool)
    registry.register(FakeSubmitTool())

    checkpoint_mgr = CheckpointManager(str(tmp_path))
    agent = AgentLoop(
        provider=provider,
        tools=registry,
        max_iterations=10,
        use_planning=False,
        checkpoint_manager=checkpoint_mgr,
    )
    # Manually set retry count to simulate prior failures
    agent._verify_retry_count = 1
    result = agent.run("check")

    assert "diff --git" in result
    # Reset after successful verify
    assert agent._verify_retry_count == 0


def test_no_checkpoint_manager_skips_rollback(tmp_path):
    """Without checkpoint_manager, verify failure doesn't trigger rollback (existing behavior)."""
    verify_tool = FakeVerifyTool(fail_count=99)

    responses = [
        LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="verify", arguments={"scope": "full"})]),
        LLMResponse(content="", tool_calls=[ToolCall(id="t2", name="submit", arguments={})]),
    ]

    provider = MagicMock()
    provider.complete.side_effect = responses

    registry = ToolRegistry()
    registry.register(verify_tool)
    registry.register(FakeSubmitTool())

    agent = AgentLoop(
        provider=provider,
        tools=registry,
        max_iterations=10,
        use_planning=False,
        checkpoint_manager=None,  # No checkpoint manager
    )
    result = agent.run("fix bug")

    # Still completes (no rollback path, falls through)
    assert "diff --git" in result
    assert agent._verify_retry_count == 0
