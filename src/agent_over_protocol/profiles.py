# Copyright (c) 2026 Danny Kim
"""Agent profile definitions served by the same A2A host."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentProfile:
    """Configuration for one public A2A agent surface."""

    name: str
    description: str
    rpc_path: str
    card_path: str
    standard_card_path: str | None
    skill_id: str
    skill_name: str
    skill_description: str
    skill_tags: tuple[str, ...]
    skill_examples: tuple[str, ...]
    system_prompt: str | None = None


RAYMOND_SYSTEM_PROMPT = (
    "You are Raymond, a warm, direct, and practical AI friend. "
    "Reply conversationally, keep momentum, and be useful without sounding formal."
)

RAYMOND_PROFILE = AgentProfile(
    name="Raymond",
    description="A friendly async A2A companion backed by OpenRouter.",
    rpc_path="/raymond/a2a",
    card_path="/.well-known/raymond.json",
    standard_card_path=None,
    skill_id="raymond-chat",
    skill_name="Raymond Chat",
    skill_description="Responds as Raymond through an async LLM backend.",
    skill_tags=("chat", "friend", "openrouter"),
    skill_examples=(
        "Hey Raymond, help me think this through.",
        "Give me a practical next step.",
    ),
    system_prompt=RAYMOND_SYSTEM_PROMPT,
)
