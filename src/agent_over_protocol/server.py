# Copyright (c) 2026 Danny Kim
"""ASGI server factory for the A2A agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from agent_over_protocol.agent_card import build_agent_card
from agent_over_protocol.executor import OpenRouterAgentExecutor
from agent_over_protocol.llm import ChatBackend, OpenRouterBackend
from agent_over_protocol.profiles import RAYMOND_PROFILE, AgentProfile
from agent_over_protocol.settings import Settings, normalize_path

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

    routes = [
        Route("/healthz", _health, methods=["GET"]),
        *_agent_routes(
            resolved_settings,
            resolved_backend,
            _default_profile(resolved_settings),
        ),
        *_agent_routes(resolved_settings, resolved_backend, RAYMOND_PROFILE),
    ]
    return Starlette(routes=routes)


def _default_profile(settings: Settings) -> AgentProfile:
    return AgentProfile(
        name=settings.agent_name,
        description=settings.agent_description,
        rpc_path=settings.agent_rpc_path,
        card_path=settings.agent_card_path,
        standard_card_path=settings.agent_standard_card_path,
        skill_id="general-chat",
        skill_name="General Chat",
        skill_description="Responds to text prompts through an async LLM backend.",
        skill_tags=("chat", "assistant", "openrouter"),
        skill_examples=(
            "Summarize this thread.",
            "Draft a concise reply.",
        ),
    )


def _agent_routes(
    settings: Settings,
    backend: ChatBackend,
    profile: AgentProfile,
) -> list[Route]:
    agent_card = build_agent_card(settings, profile)
    request_handler = DefaultRequestHandler(
        agent_executor=OpenRouterAgentExecutor(
            backend,
            system_prompt=profile.system_prompt,
        ),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )

    return [
        *_agent_card_routes(profile, agent_card),
        *_jsonrpc_routes(profile, request_handler),
    ]


def _agent_card_routes(
    profile: AgentProfile,
    agent_card: AgentCard,
) -> list[Route]:
    paths = [profile.card_path]
    if profile.standard_card_path is not None:
        paths.append(profile.standard_card_path)

    routes: list[Route] = []
    for path in _unique_paths(paths):
        routes.extend(create_agent_card_routes(agent_card, card_url=path))
    return routes


def _jsonrpc_routes(
    profile: AgentProfile,
    request_handler: DefaultRequestHandler,
) -> list[Route]:
    routes: list[Route] = []
    for path in _unique_paths([profile.rpc_path]):
        routes.extend(
            create_jsonrpc_routes(
                request_handler=request_handler,
                rpc_url=path,
                enable_v0_3_compat=True,
            )
        )
    return routes


def _unique_paths(paths: list[str]) -> list[str]:
    unique: list[str] = []
    for path in paths:
        normalized = normalize_path(path)
        if normalized not in unique:
            unique.append(normalized)
    return unique
