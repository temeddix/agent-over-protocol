# Copyright (c) 2026 Danny Kim
"""Async LLM backends for the A2A agent."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, cast

from openai import AsyncOpenAI, OpenAIError

from agent_over_protocol.tools import ToolCallError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from openai.types.chat import (
        ChatCompletionAssistantMessageParam,
        ChatCompletionMessageParam,
        ChatCompletionMessageToolCall,
        ChatCompletionMessageToolCallParam,
    )

    from agent_over_protocol.settings import Settings
    from agent_over_protocol.tools import AgentTool

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_TIMEOUT_SECONDS = 60.0
WORKSPACE_TOOL_INSTRUCTIONS = (
    "You may inspect the mounted read-only workspace only through the provided "
    "file tools. Use list_files, read_file, and search_files when the user asks "
    "about files, folders, spreadsheets, Word documents, PowerPoint decks, or "
    "other workspace documents. Never claim you inspected a file unless a tool "
    "result supports it."
)
ChatRole = Literal["user", "assistant"]


class ModelBackendError(RuntimeError):
    """Raised when the model backend cannot produce a usable response."""


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A prior conversational message to include in model context."""

    role: ChatRole
    content: str


class ChatBackend(Protocol):
    """Async chat backend used by the A2A executor."""

    async def complete(
        self,
        prompt: str,
        *,
        instructions: str | None = None,
        history: Sequence[ChatMessage] = (),
        tools: Sequence[AgentTool] = (),
    ) -> str:
        """Return a response for a user prompt."""


class OpenRouterBackend:
    """OpenRouter implementation backed by the OpenAI-compatible API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
        max_tool_rounds: int,
    ) -> None:
        """Initialize the async OpenRouter client."""
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
        )
        self._model = model
        self._max_tool_rounds = max_tool_rounds

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenRouterBackend:
        """Create an OpenRouter backend from application settings."""
        api_key = settings.openrouter_api_key
        if not api_key:
            message = "OPENROUTER_API_KEY is required"
            raise ModelBackendError(message)
        return cls(
            api_key=api_key,
            model=settings.openrouter_model,
            base_url=OPENROUTER_BASE_URL,
            timeout_seconds=OPENROUTER_TIMEOUT_SECONDS,
            max_tool_rounds=settings.agent_tool_max_rounds,
        )

    async def complete(
        self,
        prompt: str,
        *,
        instructions: str | None = None,
        history: Sequence[ChatMessage] = (),
        tools: Sequence[AgentTool] = (),
    ) -> str:
        """Return an OpenRouter chat completion for the prompt."""
        if tools:
            return await self._complete_with_tools(
                prompt,
                instructions=instructions,
                history=history,
                tools=tools,
            )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=_messages(prompt, instructions=instructions, history=history),
            )
        except OpenAIError as exc:
            message = "OpenRouter request failed"
            raise ModelBackendError(message) from exc

        if not response.choices:
            message = "OpenRouter returned no choices"
            raise ModelBackendError(message)

        content = response.choices[0].message.content
        if isinstance(content, str) and content.strip():
            return content

        message = "OpenRouter returned an empty response"
        raise ModelBackendError(message)

    async def _complete_with_tools(
        self,
        prompt: str,
        *,
        instructions: str | None,
        history: Sequence[ChatMessage],
        tools: Sequence[AgentTool],
    ) -> str:
        messages = _messages(
            prompt,
            instructions=_combine_instructions(
                instructions,
                WORKSPACE_TOOL_INSTRUCTIONS,
            ),
            history=history,
        )
        tool_index = {tool.name: tool for tool in tools}
        openai_tools = [tool.as_openai_tool() for tool in tools]

        for _ in range(self._max_tool_rounds):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=openai_tools,
                    tool_choice="auto",
                )
            except OpenAIError as exc:
                message = "OpenRouter request failed"
                raise ModelBackendError(message) from exc

            if not response.choices:
                message = "OpenRouter returned no choices"
                raise ModelBackendError(message)

            assistant_message = response.choices[0].message
            tool_calls = _function_tool_calls(assistant_message.tool_calls or [])
            if not tool_calls:
                content = assistant_message.content
                if isinstance(content, str) and content.strip():
                    return content
                message = "OpenRouter returned an empty response"
                raise ModelBackendError(message)

            messages.append(
                _assistant_tool_message(
                    content=assistant_message.content,
                    tool_calls=tool_calls,
                )
            )
            for tool_call in tool_calls:
                tool_message: ChatCompletionMessageParam = {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": await _execute_tool_call(tool_call, tool_index),
                }
                messages.append(tool_message)

        message = "OpenRouter did not produce a final response after tool use"
        raise ModelBackendError(message)


def _messages(
    prompt: str,
    *,
    instructions: str | None,
    history: Sequence[ChatMessage] = (),
) -> list[ChatCompletionMessageParam]:
    messages: list[ChatCompletionMessageParam] = []
    system_instructions = (instructions or "").strip()
    if system_instructions:
        messages.append({"role": "system", "content": system_instructions})
    for message in history:
        content = message.content.strip()
        if content:
            messages.append(
                cast(
                    "ChatCompletionMessageParam",
                    {"role": message.role, "content": content},
                )
            )
    messages.append({"role": "user", "content": prompt})
    return messages


def _combine_instructions(*parts: str | None) -> str | None:
    present = [part.strip() for part in parts if part and part.strip()]
    if not present:
        return None
    return "\n\n".join(present)


def _assistant_tool_message(
    *,
    content: object,
    tool_calls: Sequence[ChatCompletionMessageToolCall],
) -> ChatCompletionAssistantMessageParam:
    return {
        "role": "assistant",
        "content": content if isinstance(content, str) else None,
        "tool_calls": [_tool_call_param(tool_call) for tool_call in tool_calls],
    }


def _tool_call_param(
    tool_call: ChatCompletionMessageToolCall,
) -> ChatCompletionMessageToolCallParam:
    return {
        "id": tool_call.id,
        "type": "function",
        "function": {
            "name": tool_call.function.name,
            "arguments": tool_call.function.arguments,
        },
    }


def _function_tool_calls(
    tool_calls: Sequence[object],
) -> list[ChatCompletionMessageToolCall]:
    return [
        cast("ChatCompletionMessageToolCall", tool_call)
        for tool_call in tool_calls
        if getattr(tool_call, "type", None) == "function"
    ]


async def _execute_tool_call(
    tool_call: ChatCompletionMessageToolCall,
    tools: Mapping[str, AgentTool],
) -> str:
    tool = tools.get(tool_call.function.name)
    if tool is None:
        return json.dumps(
            {"kind": "error", "error": f"Unknown tool: {tool_call.function.name}"},
            ensure_ascii=False,
        )
    try:
        arguments = _tool_arguments(tool_call.function.arguments)
        return await tool.call(arguments)
    except (ToolCallError, json.JSONDecodeError) as exc:
        return json.dumps(
            {"kind": "error", "error": f"Tool call failed: {exc}"},
            ensure_ascii=False,
        )


def _tool_arguments(raw_arguments: str) -> Mapping[str, object]:
    parsed = json.loads(raw_arguments or "{}")
    if not isinstance(parsed, dict):
        message = "Tool arguments must be a JSON object"
        raise ToolCallError(message)
    return cast("Mapping[str, object]", parsed)
