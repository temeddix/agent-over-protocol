# Copyright (c) 2026 Danny Kim
"""Runtime instruction loading for model prompts."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from agent_over_protocol.settings import Settings


class ContextLoadError(RuntimeError):
    """Raised when runtime context cannot be loaded."""


class InstructionProvider(Protocol):
    """Async provider for model instructions."""

    async def load(self) -> str | None:
        """Load instructions for the next model call."""


@dataclass(frozen=True)
class FileInstructionProvider:
    """Load runtime instructions from command text and an optional file."""

    context_file: Path | None
    command: str | None
    max_chars: int

    @classmethod
    def from_settings(cls, settings: Settings) -> FileInstructionProvider:
        """Create a file-backed instruction provider from settings."""
        context_file = (
            Path(settings.agent_context_file)
            if settings.agent_context_file is not None
            else None
        )
        return cls(
            context_file=context_file,
            command=settings.agent_context_command,
            max_chars=settings.agent_context_max_chars,
        )

    async def load(self) -> str | None:
        """Load runtime instructions for a model request."""
        parts: list[str] = []
        command = (self.command or "").strip()
        if command:
            parts.append(f"Runtime command:\n{command}")

        context = await self._load_context_file()
        if context:
            name = (
                self.context_file.name if self.context_file is not None else "context"
            )
            parts.append(f"Context file ({name}):\n{context}")

        if not parts:
            return None
        return "\n\n".join(parts)

    async def _load_context_file(self) -> str | None:
        if self.context_file is None:
            return None

        try:
            content = await asyncio.to_thread(
                self.context_file.read_text,
                encoding="utf-8",
            )
        except FileNotFoundError:
            return None
        except OSError as exc:
            message = "Agent context file could not be read"
            raise ContextLoadError(message) from exc

        stripped = content.strip()
        if not stripped:
            return None
        return _truncate(stripped, self.max_chars)


def _truncate(content: str, max_chars: int) -> str:
    if max_chars <= 0 or len(content) <= max_chars:
        return content
    truncated = content[:max_chars].rstrip()
    return f"{truncated}\n\n[Context truncated to {max_chars} characters.]"
