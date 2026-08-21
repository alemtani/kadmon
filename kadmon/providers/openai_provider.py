"""OpenAI provider for kadmon."""

import json
import time
from collections.abc import Iterator

import openai

from kadmon.providers.base import LLMResponse, Message, StreamChunk, StreamEvent, TokenUsage, ToolCall

_MAX_RETRIES = 3


class OpenAIProvider:
    """LLM provider using OpenAI API (GPT-4o, o1, etc.)."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str = "",
        max_tokens: int = 8192,
        base_url: str = "",
        default_headers: dict[str, str] | None = None,
    ) -> None:
        """Create an OpenAI-compatible client.

        A non-empty base_url points this at a compatible endpoint.
        `default_headers` carries client identity. Keep credentials out of it —
        `api_key` already becomes the one auth header.
        """
        self.model = model
        self.max_tokens = max_tokens
        self.base_url = base_url
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url or None,
            default_headers=default_headers or None,
        )

    def complete(
        self, messages: list[Message], tools: list[dict] | None = None, system: str = ""
    ) -> LLMResponse:
        oai_messages = self._build_messages(messages, system)

        kwargs: dict = {
            "model": self.model,
            "messages": oai_messages,
            "max_completion_tokens": self.max_tokens,
        }
        if tools:
            kwargs["tools"] = [self._convert_tool(t) for t in tools]

        response = self._call_with_retry(kwargs)
        return self._parse_response(response)

    def stream(
        self, messages: list[Message], tools: list[dict] | None = None, system: str = ""
    ) -> Iterator[StreamChunk]:
        """Stream response chunks as they arrive."""
        oai_messages = self._build_messages(messages, system)
        kwargs: dict = {
            "model": self.model,
            "messages": oai_messages,
            "max_completion_tokens": self.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = [self._convert_tool(t) for t in tools]

        # Through _call_with_retry, not the client directly: a subclass that
        # refreshes a token or stops on a spent pool must see this call too.
        response_stream = self._call_with_retry(kwargs)
        yield from self._process_stream(response_stream)

    def _build_messages(self, messages: list[Message], system: str) -> list[dict]:
        """Build OpenAI message list from internal messages."""
        oai_messages: list[dict] = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        for msg in messages:
            converted = self._convert_message(msg)
            if isinstance(converted, dict) and "_multi" in converted:
                oai_messages.extend(converted["_multi"])
            else:
                oai_messages.append(converted)
        return oai_messages

    def _process_stream(self, response_stream) -> Iterator[StreamChunk]:
        """Process OpenAI streaming chunks into StreamChunk events."""
        content_parts: list[str] = []
        tool_calls_acc: dict[int, dict] = {}  # index -> {id, name, arguments_json}
        input_tokens = 0
        output_tokens = 0
        stop_reason = ""

        for chunk in response_stream:
            if chunk.usage:
                input_tokens = chunk.usage.prompt_tokens
                output_tokens = chunk.usage.completion_tokens

            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            if choice.finish_reason:
                stop_reason = choice.finish_reason

            delta = choice.delta
            if delta and delta.content:
                content_parts.append(delta.content)
                yield StreamChunk(event=StreamEvent.TEXT_DELTA, text=delta.content)

            if delta and delta.tool_calls:
                yield from self._handle_tool_delta(delta.tool_calls, tool_calls_acc)

        tool_calls = self._finalize_tool_calls(tool_calls_acc)
        for tc in tool_calls:
            yield StreamChunk(event=StreamEvent.TOOL_END, tool_name=tc.name, tool_id=tc.id)
        response = LLMResponse(
            content="".join(content_parts),
            tool_calls=tool_calls,
            usage=TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens),
            stop_reason=stop_reason,
        )
        yield StreamChunk(event=StreamEvent.DONE, response=response)

    def _handle_tool_delta(
        self, tc_deltas: list, tool_calls_acc: dict[int, dict]
    ) -> Iterator[StreamChunk]:
        """Handle tool call deltas from a streaming chunk."""
        for tc_delta in tc_deltas:
            idx = tc_delta.index
            if idx not in tool_calls_acc:
                tool_calls_acc[idx] = {
                    "id": tc_delta.id or "",
                    "name": tc_delta.function.name if tc_delta.function else "",
                    "arguments_json": "",
                }
                if tool_calls_acc[idx]["name"]:
                    yield StreamChunk(
                        event=StreamEvent.TOOL_START,
                        tool_name=tool_calls_acc[idx]["name"],
                        tool_id=tool_calls_acc[idx]["id"],
                    )
            if tc_delta.function and tc_delta.function.arguments:
                tool_calls_acc[idx]["arguments_json"] += tc_delta.function.arguments
                yield StreamChunk(
                    event=StreamEvent.TOOL_DELTA,
                    text=tc_delta.function.arguments,
                    tool_name=tool_calls_acc[idx]["name"],
                )

    def _finalize_tool_calls(self, tool_calls_acc: dict[int, dict]) -> list[ToolCall]:
        """Assemble accumulated tool call fragments into ToolCall objects."""
        tool_calls: list[ToolCall] = []
        for idx in sorted(tool_calls_acc):
            tc = tool_calls_acc[idx]
            try:
                args = json.loads(tc["arguments_json"]) if tc["arguments_json"] else {}
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=tc["id"], name=tc["name"], arguments=args))
        return tool_calls

    def _convert_message(self, msg: Message) -> dict:
        if isinstance(msg.content, list):
            if msg.role == "assistant":
                content = ""
                tool_calls = []
                for block in msg.content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            content = block.get("text", "")
                        elif block.get("type") == "tool_use":
                            tool_calls.append(
                                {
                                    "id": block["id"],
                                    "type": "function",
                                    "function": {
                                        "name": block["name"],
                                        "arguments": json.dumps(block.get("input", {})),
                                    },
                                }
                            )
                result: dict = {"role": "assistant", "content": content or None}
                if tool_calls:
                    result["tool_calls"] = tool_calls
                return result
            else:
                # Tool results — OpenAI expects each as a separate role='tool' message
                results = []
                for block in msg.content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        results.append(
                            {
                                "role": "tool",
                                "tool_call_id": block["tool_use_id"],
                                "content": block.get("content", ""),
                            }
                        )
                if len(results) == 1:
                    return results[0]
                return {"_multi": results}
        return {"role": msg.role, "content": msg.content}

    def _convert_tool(self, tool: dict) -> dict:
        """Convert internal tool format to OpenAI function format."""
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        }

    def _call_with_retry(self, kwargs: dict):
        for attempt in range(_MAX_RETRIES):
            try:
                return self.client.chat.completions.create(**kwargs)
            except (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError):
                if attempt == _MAX_RETRIES - 1:
                    raise
                time.sleep(2**attempt)
        raise RuntimeError("Unreachable")

    def _parse_response(self, response) -> LLMResponse:
        choice = response.choices[0]
        msg = choice.message

        content = msg.content or ""
        tool_calls = []

        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=TokenUsage(
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
            ),
            stop_reason=choice.finish_reason or "",
        )
