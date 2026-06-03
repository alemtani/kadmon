# Streaming Parity

## Problem

Only Anthropic and Bedrock providers had `stream()` methods. The agent loop selects streaming
via `hasattr(provider, 'stream')`, so OpenAI and Gemini fell back to non-streaming `complete()`.
This meant no incremental text display for those providers.

## Interface Contract

All providers expose the same streaming interface (defined in `base.py`):

```python
def stream(messages: list[Message], tools: list[dict] | None, system: str) -> Iterator[StreamChunk]
```

StreamChunk events yielded in order:
- `TEXT_DELTA` — incremental text content (`.text` field)
- `TOOL_START` — tool call begins (`.tool_name`, `.tool_id`)
- `TOOL_DELTA` — tool arguments fragment (`.text`, `.tool_name`)
- `TOOL_END` — tool call complete (`.tool_name`, `.tool_id`)
- `DONE` — final event, carries assembled `LLMResponse` (`.response`)

The `DONE` chunk's `response` has: `content` (full text), `tool_calls` (list of ToolCall),
`usage` (TokenUsage), and `stop_reason`.

## Provider Mapping

### OpenAI

Uses `stream=True` + `stream_options={"include_usage": True}` on `chat.completions.create`.
- `delta.content` → `TEXT_DELTA`
- `delta.tool_calls[i]` with index-based accumulation → `TOOL_START` / `TOOL_DELTA` / `TOOL_END`
- Final chunk with `usage` field → token counts
- `choice.finish_reason` → `stop_reason`

### Gemini

Uses `client.models.generate_content_stream()`.
- `part.text` → `TEXT_DELTA`
- `part.function_call` → `TOOL_START` + `TOOL_END` (Gemini sends complete function calls per chunk)
- `chunk.usage_metadata` → token counts
- `candidate.finish_reason.name` → `stop_reason`

## Testing

`tests/test_provider_streaming.py` mocks SDK clients (no network) and verifies for each provider:
1. Text deltas stream incrementally (multiple TEXT_DELTA events)
2. Final DONE message assembles full content with correct usage
3. Tool calls are captured with correct names and arguments

## Files Changed

- `kadmon/providers/openai_provider.py` — added `stream()`, `_build_messages()`, `_process_stream()`, `_handle_tool_delta()`, `_finalize_tool_calls()`
- `kadmon/providers/gemini.py` — added `stream()`, `_process_stream()`
- `tests/test_provider_streaming.py` — new test file (6 tests)
