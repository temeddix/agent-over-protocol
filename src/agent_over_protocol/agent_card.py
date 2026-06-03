# Copyright (c) 2026 Danny Kim
"""Agent card construction for invitability and A2A discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentProvider,
    AgentSkill,
)
from a2a.utils.constants import PROTOCOL_VERSION_0_3, PROTOCOL_VERSION_1_0

if TYPE_CHECKING:
    from agent_over_protocol.settings import Settings


TEXT_MIME_TYPE = "text/plain"


def build_agent_card(settings: Settings) -> AgentCard:
    """Build the public A2A agent card."""
    return AgentCard(
        name=settings.agent_name,
        description=settings.agent_description,
        version=settings.agent_version,
        provider=AgentProvider(
            organization="Agent Over Protocol",
            url=settings.agent_base_url,
        ),
        supported_interfaces=[
            AgentInterface(
                url=settings.rpc_url,
                protocol_binding="JSONRPC",
                protocol_version=PROTOCOL_VERSION_0_3,
            ),
            AgentInterface(
                url=settings.rpc_url,
                protocol_binding="JSONRPC",
                protocol_version=PROTOCOL_VERSION_1_0,
            ),
        ],
        capabilities=AgentCapabilities(
            streaming=True,
            push_notifications=False,
            extended_agent_card=False,
        ),
        default_input_modes=[TEXT_MIME_TYPE],
        default_output_modes=[TEXT_MIME_TYPE],
        skills=[
            AgentSkill(
                id="general-chat",
                name="Workspace Chat",
                description=(
                    "Responds to text prompts and can inspect mounted workspace "
                    "files, folders, and common document formats."
                ),
                tags=["chat", "assistant", "files", "documents"],
                examples=[
                    "Summarize AGENTS.md.",
                    "List the available workspace documents.",
                ],
                input_modes=[TEXT_MIME_TYPE],
                output_modes=[TEXT_MIME_TYPE],
            )
        ],
    )
