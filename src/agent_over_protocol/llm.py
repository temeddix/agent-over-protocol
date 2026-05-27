# Copyright (c) 2026 Danny Kim
"""Async LLM backends for the A2A agent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from openai import AsyncOpenAI, OpenAIError

if TYPE_CHECKING:
    from agent_over_protocol.settings import Settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "openai/gpt-4.1-mini"
OPENROUTER_TIMEOUT_SECONDS = 60.0


class ModelBackendError(RuntimeError):
    """Raised when the model backend cannot produce a usable response."""


class ChatBackend(Protocol):
    """Async chat backend used by the A2A executor."""

    async def complete(self, prompt: str) -> str:
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
    ) -> None:
        """Initialize the async OpenRouter client."""
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
        )
        self._model = model

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenRouterBackend:
        """Create an OpenRouter backend from application settings."""
        api_key = settings.openrouter_api_key
        if not api_key:
            message = "OPENROUTER_API_KEY is required"
            raise ModelBackendError(message)
        return cls(
            api_key=api_key,
            model=OPENROUTER_MODEL,
            base_url=OPENROUTER_BASE_URL,
            timeout_seconds=OPENROUTER_TIMEOUT_SECONDS,
        )

    async def complete(self, prompt: str) -> str:
        """Return an OpenRouter chat completion for the prompt."""
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
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
