"""Tests for context-budget transparency and token accounting accessors."""

from unittest.mock import MagicMock

from kadmon.agent.context import ContextManager, ContextStats
from kadmon.agent.loop import AgentLoop, UsageSummary
from kadmon.providers.base import (
    LLMResponse,
    Message,
    StreamChunk,
    StreamEvent,
    TokenUsage,
    ToolCall,
)
from kadmon.tools.base import Tool, ToolRegistry, ToolResult


# --- ContextManager.stats() tests ---


def test_stats_empty():
    cm = ContextManager(max_tokens=200000)
    s = cm.stats()
    assert s == ContextStats(
        used_tokens=0, max_tokens=200000, utilization=0.0, message_count=0, near_handoff=False
    )


def test_stats_after_messages():
    cm = ContextManager(max_tokens=1000)
    cm.add(Message(role="user", content="hello world"))  # ~11 chars => 2 tokens
    cm.add(Message(role="assistant", content="hi"))  # ~2 chars => 0 tokens
    s = cm.stats()
    assert s.used_tokens == cm._token_estimate
    assert s.max_tokens == 1000
    assert s.message_count == 2
    assert s.utilization == s.used_tokens / 1000
    assert not s.near_handoff


def test_stats_near_handoff_boundary():
    cm = ContextManager(max_tokens=100)
    # Add enough to reach exactly 0.8 utilization (80 tokens => 320 chars)
    cm.add(Message(role="user", content="a" * 320))
    assert cm.stats().near_handoff is True

    # Just below boundary
    cm2 = ContextManager(max_tokens=100)
    cm2.add(Message(role="user", content="a" * 316))  # 316//4 = 79 tokens => 0.79
    assert cm2.stats().near_handoff is False


def test_stats_returns_frozen_dataclass():
    cm = ContextManager(max_tokens=100)
    s = cm.stats()
    assert isinstance(s, ContextStats)


# --- AgentLoop.usage_summary() tests ---


class FakeSubmit(Tool):
    name = "submit"
    description = "submit"
    parameters = {"type": "object", "properties": {}, "required": []}

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(output="patch")


class FakeDummy(Tool):
    name = "dummy"
    description = "dummy"
    parameters = {"type": "object", "properties": {}, "required": []}

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(output="ok")


def test_usage_summary_initial():
    provider = MagicMock()
    provider.complete.return_value = LLMResponse(
        content="", tool_calls=[ToolCall(id="1", name="submit", arguments={})],
        usage=TokenUsage(input_tokens=100, output_tokens=50),
    )
    registry = ToolRegistry()
    registry.register(FakeSubmit())
    agent = AgentLoop(provider=provider, tools=registry, max_iterations=5)

    # Before any run
    s = agent.usage_summary()
    assert s == UsageSummary(input_tokens=0, output_tokens=0, total_tokens=0, turns=0)


def test_usage_summary_non_streaming():
    provider = MagicMock()
    # Turn 1: dummy tool
    resp1 = LLMResponse(
        content="", tool_calls=[ToolCall(id="1", name="dummy", arguments={})],
        usage=TokenUsage(input_tokens=100, output_tokens=50),
    )
    # Turn 2: submit
    resp2 = LLMResponse(
        content="", tool_calls=[ToolCall(id="2", name="submit", arguments={})],
        usage=TokenUsage(input_tokens=200, output_tokens=80),
    )
    provider.complete.side_effect = [resp1, resp2]

    registry = ToolRegistry()
    registry.register(FakeDummy())
    registry.register(FakeSubmit())
    agent = AgentLoop(provider=provider, tools=registry, max_iterations=5)
    agent.run("task")

    s = agent.usage_summary()
    assert s.input_tokens == 300
    assert s.output_tokens == 130
    assert s.total_tokens == 430
    assert s.turns == 2


def test_usage_summary_streaming():
    """Token accounting works via streaming path (display + provider.stream)."""
    provider = MagicMock()
    display = MagicMock()
    display.handle = MagicMock()

    # Streaming provider yields chunks ending with DONE carrying usage
    def fake_stream(**kwargs):
        yield StreamChunk(event=StreamEvent.TEXT_DELTA, text="hi")
        yield StreamChunk(
            event=StreamEvent.DONE,
            response=LLMResponse(
                content="",
                tool_calls=[ToolCall(id="1", name="submit", arguments={})],
                usage=TokenUsage(input_tokens=150, output_tokens=60),
            ),
        )

    provider.stream = fake_stream

    registry = ToolRegistry()
    registry.register(FakeSubmit())
    agent = AgentLoop(provider=provider, tools=registry, max_iterations=5, display=display)
    agent.run("task")

    s = agent.usage_summary()
    assert s.input_tokens == 150
    assert s.output_tokens == 60
    assert s.total_tokens == 210
    assert s.turns == 1


def test_usage_summary_accumulates_across_turns():
    provider = MagicMock()
    responses = [
        LLMResponse(
            content="", tool_calls=[ToolCall(id=str(i), name="dummy", arguments={})],
            usage=TokenUsage(input_tokens=10 * (i + 1), output_tokens=5 * (i + 1)),
        )
        for i in range(4)
    ]
    responses.append(
        LLMResponse(
            content="", tool_calls=[ToolCall(id="5", name="submit", arguments={})],
            usage=TokenUsage(input_tokens=50, output_tokens=25),
        )
    )
    provider.complete.side_effect = responses

    registry = ToolRegistry()
    registry.register(FakeDummy())
    registry.register(FakeSubmit())
    agent = AgentLoop(provider=provider, tools=registry, max_iterations=10)
    agent.run("task")

    s = agent.usage_summary()
    # input: 10+20+30+40+50=150, output: 5+10+15+20+25=75
    assert s.input_tokens == 150
    assert s.output_tokens == 75
    assert s.total_tokens == 225
    assert s.turns == 5
