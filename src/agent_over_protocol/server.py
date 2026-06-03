# Copyright (c) 2026 Danny Kim
"""ASGI server factory for the A2A agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from a2a.server.agent_execution import SimpleRequestContextBuilder
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from agent_over_protocol.agent_card import build_agent_card
from agent_over_protocol.context import FileInstructionProvider
from agent_over_protocol.executor import OpenRouterAgentExecutor
from agent_over_protocol.llm import ChatBackend, OpenRouterBackend
from agent_over_protocol.settings import Settings, normalize_path
from agent_over_protocol.tools import build_workspace_tools

if TYPE_CHECKING:
    from a2a.types import AgentCard
    from starlette.requests import Request
    from starlette.responses import Response


async def _health(_: Request) -> Response:
    return JSONResponse({"status": "ok"})


def create_app(
    *,
    settings: Settings | None = None,
    backend: ChatBackend | None = None,
) -> Starlette:
    """Create the A2A ASGI application."""
    resolved_settings = settings or Settings()
    resolved_backend = backend or OpenRouterBackend.from_settings(resolved_settings)
    instruction_provider = FileInstructionProvider.from_settings(resolved_settings)
    tools = build_workspace_tools(resolved_settings)
    agent_card = build_agent_card(resolved_settings)
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=OpenRouterAgentExecutor(
            resolved_backend,
            instruction_provider=instruction_provider,
            tools=tools,
        ),
        task_store=task_store,
        agent_card=agent_card,
        request_context_builder=SimpleRequestContextBuilder(
            should_populate_referred_tasks=True,
            task_store=task_store,
        ),
    )

    routes = [
        Route("/healthz", _health, methods=["GET"]),
        *create_agent_card_routes(
            agent_card,
            card_url=normalize_path(resolved_settings.agent_card_path),
        ),
        *_extra_agent_card_routes(resolved_settings, agent_card),
        *create_jsonrpc_routes(
            request_handler=request_handler,
            rpc_url=normalize_path(resolved_settings.agent_rpc_path),
            enable_v0_3_compat=True,
        ),
    ]
    return Starlette(routes=routes)


def _extra_agent_card_routes(
    settings: Settings,
    agent_card: AgentCard,
) -> list[Route]:
    primary_path = normalize_path(settings.agent_card_path)
    standard_path = normalize_path(settings.agent_standard_card_path)
    if standard_path == primary_path:
        return []
    return create_agent_card_routes(agent_card, card_url=standard_path)
