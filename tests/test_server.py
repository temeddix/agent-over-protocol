# Copyright (c) 2026 Danny Kim
"""Tests for the A2A ASGI server."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import httpx

from agent_over_protocol.server import create_app
from agent_over_protocol.settings import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


A2A_V1_HEADERS = {"A2A-Version": "1.0"}


class FakeBackend:
    """Async backend double for server tests."""

    def __init__(self, response: str = "Hello from the test backend.") -> None:
        """Initialize the fake backend."""
        self.response = response
        self.prompts: list[str] = []

    async def complete(self, prompt: str) -> str:
        """Capture the prompt and return the configured response."""
        self.prompts.append(prompt)
        return self.response


@asynccontextmanager
async def _client(backend: FakeBackend) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(agent_base_url="https://agent.example.com")
    app = create_app(settings=settings, backend=backend)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client


async def test_agent_card_is_invitable() -> None:
    """The agent card is available at the URL used by invite flows."""
    backend = FakeBackend()
    async with _client(backend) as client:
        response = await client.get("/.well-known/agent.json")

    assert response.status_code == httpx.codes.OK
    body = response.json()
    response_text = response.text

    assert body["name"] == "Agent Over Protocol"
    assert body["url"] == "https://agent.example.com/a2a"
    assert body["preferredTransport"] == "JSONRPC"
    assert body["supportedInterfaces"][0]["url"] == "https://agent.example.com/a2a"
    assert body["skills"][0]["id"] == "general-chat"
    assert "OPENROUTER_API_KEY" not in response_text
    assert "test-openrouter-api-key" not in response_text


async def test_standard_agent_card_path_is_available() -> None:
    """The SDK standard agent-card path is also served."""
    backend = FakeBackend()
    async with _client(backend) as client:
        response = await client.get("/.well-known/agent-card.json")

    assert response.status_code == httpx.codes.OK
    assert response.json()["name"] == "Agent Over Protocol"


async def test_send_message_returns_completed_task() -> None:
    """A JSON-RPC SendMessage request receives the backend answer."""
    backend = FakeBackend(response="A2A test response")
    async with _client(backend) as client:
        response = await client.post(
            "/a2a",
            headers=A2A_V1_HEADERS,
            json=_send_message_request("hello"),
        )

    assert response.status_code == httpx.codes.OK
    assert backend.prompts == ["hello"]

    body = response.json()
    assert body["id"] == "request-1"

    task = body["result"]["task"]
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert task["status"]["message"]["parts"] == [{"text": "A2A test response"}]
    assert task["artifacts"][0]["name"] == "response"
    assert task["artifacts"][0]["parts"] == [{"text": "A2A test response"}]
    assert task["history"][0]["parts"] == [{"text": "hello"}]


async def test_streaming_message_emits_artifact_and_completed_status() -> None:
    """A streaming JSON-RPC request exposes text as an artifact update."""
    backend = FakeBackend(response="Streaming A2A response")
    async with _client(backend) as client:
        response = await client.post(
            "/a2a",
            headers=A2A_V1_HEADERS,
            json=_send_streaming_message_request("stream hello"),
        )

    assert response.status_code == httpx.codes.OK
    assert backend.prompts == ["stream hello"]

    assert '"artifactUpdate"' in response.text
    assert '"text": "Streaming A2A response"' in response.text
    assert '"statusUpdate"' in response.text
    assert '"state": "TASK_STATE_COMPLETED"' in response.text


async def test_empty_message_is_rejected_without_backend_call() -> None:
    """Empty text requests are rejected before calling the backend."""
    backend = FakeBackend()
    async with _client(backend) as client:
        response = await client.post(
            "/a2a",
            headers=A2A_V1_HEADERS,
            json=_send_message_request(""),
        )

    assert response.status_code == httpx.codes.OK
    assert backend.prompts == []

    task = response.json()["result"]["task"]
    assert task["status"]["state"] == "TASK_STATE_REJECTED"


async def test_health_endpoint() -> None:
    """The health endpoint returns a small readiness payload."""
    backend = FakeBackend()
    async with _client(backend) as client:
        response = await client.get("/healthz")

    assert response.status_code == httpx.codes.OK
    assert response.json() == {"status": "ok"}


def _send_message_request(text: str) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": "request-1",
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": "message-1",
                "role": "ROLE_USER",
                "parts": [{"text": text}],
            },
            "configuration": {"acceptedOutputModes": ["text/plain"]},
        },
    }


def _send_streaming_message_request(text: str) -> dict[str, object]:
    request = _send_message_request(text)
    request["method"] = "SendStreamingMessage"
    return request
