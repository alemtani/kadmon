"""Tests for OpenAI and Gemini streaming support."""

from unittest.mock import MagicMock, patch

from kadmon.providers.base import Message, StreamEvent


# --- OpenAI streaming tests ---


def _make_oai_text_chunk(content: str, finish_reason: str | None = None):
    """Create a mock OpenAI streaming chunk with text content."""
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = None
    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = finish_reason
    chunk = MagicMock()
    chunk.choices = [choice]
    chunk.usage = None
    return chunk


def _make_oai_tool_chunk(index: int, tc_id: str | None, name: str | None, args_fragment: str):
    """Create a mock OpenAI streaming chunk with a tool call delta."""
    func = MagicMock()
    func.name = name
    func.arguments = args_fragment
    tc_delta = MagicMock()
    tc_delta.index = index
    tc_delta.id = tc_id
    tc_delta.function = func
    delta = MagicMock()
    delta.content = None
    delta.tool_calls = [tc_delta]
    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = None
    chunk = MagicMock()
    chunk.choices = [choice]
    chunk.usage = None
    return chunk


def _make_oai_usage_chunk(input_tokens: int, output_tokens: int):
    """Create a final OpenAI chunk with usage info."""
    usage = MagicMock()
    usage.prompt_tokens = input_tokens
    usage.completion_tokens = output_tokens
    chunk = MagicMock()
    chunk.choices = []
    chunk.usage = usage
    return chunk


class TestOpenAIStreaming:
    def test_text_deltas_stream_incrementally(self):
        from kadmon.providers.openai_provider import OpenAIProvider

        chunks = [
            _make_oai_text_chunk("Hello"),
            _make_oai_text_chunk(" world"),
            _make_oai_text_chunk("", "stop"),
            _make_oai_usage_chunk(10, 5),
        ]

        with patch("openai.OpenAI"):
            provider = OpenAIProvider(model="gpt-4o", api_key="test")
            provider.client = MagicMock()
            provider.client.chat.completions.create.return_value = iter(chunks)

        messages = [Message(role="user", content="hi")]
        events = list(provider.stream(messages))

        text_deltas = [e for e in events if e.event == StreamEvent.TEXT_DELTA]
        assert len(text_deltas) == 2
        assert text_deltas[0].text == "Hello"
        assert text_deltas[1].text == " world"

    def test_final_message_assembles_correctly(self):
        from kadmon.providers.openai_provider import OpenAIProvider

        chunks = [
            _make_oai_text_chunk("Hello"),
            _make_oai_text_chunk(" world"),
            _make_oai_text_chunk("", "stop"),
            _make_oai_usage_chunk(10, 5),
        ]

        with patch("openai.OpenAI"):
            provider = OpenAIProvider(model="gpt-4o", api_key="test")
            provider.client = MagicMock()
            provider.client.chat.completions.create.return_value = iter(chunks)

        messages = [Message(role="user", content="hi")]
        events = list(provider.stream(messages))

        done = [e for e in events if e.event == StreamEvent.DONE]
        assert len(done) == 1
        resp = done[0].response
        assert resp.content == "Hello world"
        assert resp.usage.input_tokens == 10
        assert resp.usage.output_tokens == 5
        assert resp.stop_reason == "stop"

    def test_tool_calls_captured(self):
        from kadmon.providers.openai_provider import OpenAIProvider

        chunks = [
            _make_oai_tool_chunk(0, "call_abc", "read_file", '{"path":'),
            _make_oai_tool_chunk(0, None, None, ' "/tmp/x"}'),
            _make_oai_text_chunk("", "tool_calls"),
            _make_oai_usage_chunk(20, 15),
        ]

        with patch("openai.OpenAI"):
            provider = OpenAIProvider(model="gpt-4o", api_key="test")
            provider.client = MagicMock()
            provider.client.chat.completions.create.return_value = iter(chunks)

        messages = [Message(role="user", content="read file")]
        events = list(provider.stream(messages))

        tool_starts = [e for e in events if e.event == StreamEvent.TOOL_START]
        assert len(tool_starts) == 1
        assert tool_starts[0].tool_name == "read_file"
        assert tool_starts[0].tool_id == "call_abc"

        tool_ends = [e for e in events if e.event == StreamEvent.TOOL_END]
        assert len(tool_ends) == 1

        done = [e for e in events if e.event == StreamEvent.DONE][0]
        assert len(done.response.tool_calls) == 1
        tc = done.response.tool_calls[0]
        assert tc.name == "read_file"
        assert tc.arguments == {"path": "/tmp/x"}


# --- Gemini streaming tests ---


def _make_gemini_text_chunk(text: str, finish_reason=None, usage=None):
    """Create a mock Gemini streaming chunk with text."""
    part = MagicMock()
    part.text = text
    part.function_call = None
    content = MagicMock()
    content.parts = [part]
    candidate = MagicMock()
    candidate.content = content
    candidate.finish_reason = finish_reason
    chunk = MagicMock()
    chunk.candidates = [candidate]
    chunk.usage_metadata = usage
    return chunk


def _make_gemini_tool_chunk(name: str, args: dict, usage=None):
    """Create a mock Gemini streaming chunk with a function call."""
    fc = MagicMock()
    fc.name = name
    fc.args = args
    part = MagicMock()
    part.text = None
    part.function_call = fc
    content = MagicMock()
    content.parts = [part]
    candidate = MagicMock()
    candidate.content = content
    candidate.finish_reason = None
    chunk = MagicMock()
    chunk.candidates = [candidate]
    chunk.usage_metadata = usage
    return chunk


def _make_gemini_usage(prompt: int, candidates: int):
    """Create mock Gemini usage metadata."""
    usage = MagicMock()
    usage.prompt_token_count = prompt
    usage.candidates_token_count = candidates
    return usage


class TestGeminiStreaming:
    def test_text_deltas_stream_incrementally(self):
        from kadmon.providers.gemini import GeminiProvider

        usage = _make_gemini_usage(12, 8)
        chunks = [
            _make_gemini_text_chunk("Hello"),
            _make_gemini_text_chunk(" world", usage=usage),
        ]

        with patch("google.genai.Client"):
            provider = GeminiProvider(model="gemini-2.5-flash", api_key="test")
            provider.client = MagicMock()
            provider.client.models.generate_content_stream.return_value = iter(chunks)

        messages = [Message(role="user", content="hi")]
        events = list(provider.stream(messages))

        text_deltas = [e for e in events if e.event == StreamEvent.TEXT_DELTA]
        assert len(text_deltas) == 2
        assert text_deltas[0].text == "Hello"
        assert text_deltas[1].text == " world"

    def test_final_message_assembles_correctly(self):
        from kadmon.providers.gemini import GeminiProvider

        finish = MagicMock()
        finish.name = "STOP"
        usage = _make_gemini_usage(12, 8)
        chunks = [
            _make_gemini_text_chunk("Hello"),
            _make_gemini_text_chunk(" world", finish_reason=finish, usage=usage),
        ]

        with patch("google.genai.Client"):
            provider = GeminiProvider(model="gemini-2.5-flash", api_key="test")
            provider.client = MagicMock()
            provider.client.models.generate_content_stream.return_value = iter(chunks)

        messages = [Message(role="user", content="hi")]
        events = list(provider.stream(messages))

        done = [e for e in events if e.event == StreamEvent.DONE]
        assert len(done) == 1
        resp = done[0].response
        assert resp.content == "Hello world"
        assert resp.usage.input_tokens == 12
        assert resp.usage.output_tokens == 8
        assert resp.stop_reason == "STOP"

    def test_tool_calls_captured(self):
        from kadmon.providers.gemini import GeminiProvider

        usage = _make_gemini_usage(15, 10)
        chunks = [
            _make_gemini_tool_chunk("read_file", {"path": "/tmp/x"}, usage=usage),
        ]

        with patch("google.genai.Client"):
            provider = GeminiProvider(model="gemini-2.5-flash", api_key="test")
            provider.client = MagicMock()
            provider.client.models.generate_content_stream.return_value = iter(chunks)

        messages = [Message(role="user", content="read")]
        events = list(provider.stream(messages))

        tool_starts = [e for e in events if e.event == StreamEvent.TOOL_START]
        assert len(tool_starts) == 1
        assert tool_starts[0].tool_name == "read_file"

        tool_ends = [e for e in events if e.event == StreamEvent.TOOL_END]
        assert len(tool_ends) == 1

        done = [e for e in events if e.event == StreamEvent.DONE][0]
        assert len(done.response.tool_calls) == 1
        tc = done.response.tool_calls[0]
        assert tc.name == "read_file"
        assert tc.arguments == {"path": "/tmp/x"}
