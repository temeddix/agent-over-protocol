# Copyright (c) 2026 Danny Kim
"""Tests for the A2A ASGI server."""

from __future__ import annotations

import tempfile
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from agent_over_protocol.server import create_app
from agent_over_protocol.settings import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from agent_over_protocol.llm import ChatMessage
    from agent_over_protocol.tools import AgentTool


A2A_V1_HEADERS = {"A2A-Version": "1.0"}


class FakeBackend:
    """Async backend double for server tests."""

    def __init__(self, response: str = "Hello from the test backend.") -> None:
        """Initialize the fake backend."""
        self.response = response
        self.prompts: list[str] = []
        self.instructions: list[str | None] = []
        self.histories: list[list[tuple[str, str]]] = []
        self.tool_names: list[list[str]] = []

    async def complete(
        self,
        prompt: str,
        *,
        instructions: str | None = None,
        history: Sequence[ChatMessage] = (),
        tools: Sequence[AgentTool] = (),
    ) -> str:
        """Capture the prompt and return the configured response."""
        self.prompts.append(prompt)
        self.instructions.append(instructions)
        self.histories.append([(message.role, message.content) for message in history])
        self.tool_names.append([tool.name for tool in tools])
        return self.response


@asynccontextmanager
async def _client(
    backend: FakeBackend,
    *,
    conversation_db_path: Path | None = None,
    settings: Settings | None = None,
) -> AsyncIterator[httpx.AsyncClient]:
    temp_dir_context = (
        tempfile.TemporaryDirectory()
        if conversation_db_path is None
        else nullcontext(None)
    )
    with temp_dir_context as temp_dir:
        if conversation_db_path is None:
            if temp_dir is None:
                raise AssertionError
            db_path = Path(temp_dir) / "conversations.sqlite"
        else:
            db_path = conversation_db_path

        if settings is None:
            resolved_settings = Settings(
                agent_base_url="https://agent.example.com",
                agent_conversation_db_path=str(db_path),
            )
        else:
            resolved_settings = settings.model_copy(
                update={"agent_conversation_db_path": str(db_path)}
            )

        app = create_app(settings=resolved_settings, backend=backend)
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
    assert backend.tool_names == [["list_files", "read_file", "search_files"]]

    body = response.json()
    assert body["id"] == "request-1"

    task = body["result"]["task"]
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert task["status"]["message"]["parts"] == [{"text": "A2A test response"}]
    assert task["artifacts"][0]["name"] == "response"
    assert task["artifacts"][0]["parts"] == [{"text": "A2A test response"}]
    assert task["history"][0]["parts"] == [{"text": "hello"}]


async def test_send_message_uses_stored_context_history() -> None:
    """Messages sharing an A2A context ID pass prior chat history to the backend."""
    backend = FakeBackend(response="First A2A response")
    async with _client(backend) as client:
        first_response = await client.post(
            "/a2a",
            headers=A2A_V1_HEADERS,
            json=_send_message_request("first question"),
        )
        first_task = first_response.json()["result"]["task"]

        backend.response = "Second A2A response"
        second_response = await client.post(
            "/a2a",
            headers=A2A_V1_HEADERS,
            json=_send_message_request(
                "second question",
                context_id=first_task["contextId"],
                message_id="message-2",
            ),
        )

    assert second_response.status_code == httpx.codes.OK
    assert backend.prompts == ["first question", "second question"]
    assert backend.histories[0] == []
    assert ("user", "first question") in backend.histories[1]
    assert ("assistant", "First A2A response") in backend.histories[1]
    assert ("user", "second question") not in backend.histories[1]


async def test_send_message_uses_fallback_history_without_context_id() -> None:
    """Clients that omit context IDs still get process-local chat continuity."""
    backend = FakeBackend(response="First A2A response")
    async with _client(backend) as client:
        first_response = await client.post(
            "/a2a",
            headers=A2A_V1_HEADERS,
            json=_send_message_request("first question"),
        )

        backend.response = "Second A2A response"
        second_response = await client.post(
            "/a2a",
            headers=A2A_V1_HEADERS,
            json=_send_message_request("second question", message_id="message-2"),
        )

    assert first_response.status_code == httpx.codes.OK
    assert second_response.status_code == httpx.codes.OK
    assert backend.prompts == ["first question", "second question"]
    assert backend.histories[0] == []
    assert ("user", "first question") in backend.histories[1]
    assert ("assistant", "First A2A response") in backend.histories[1]


async def test_send_message_uses_reference_task_history() -> None:
    """A2A reference task IDs are loaded and merged into model history."""
    backend = FakeBackend(response="First A2A response")
    async with _client(backend) as client:
        first_response = await client.post(
            "/a2a",
            headers=A2A_V1_HEADERS,
            json=_send_message_request("first question"),
        )
        first_task = first_response.json()["result"]["task"]

        backend.response = "Second A2A response"
        second_response = await client.post(
            "/a2a",
            headers=A2A_V1_HEADERS,
            json=_send_message_request(
                "second question",
                message_id="message-2",
                reference_task_ids=[first_task["id"]],
            ),
        )

    assert second_response.status_code == httpx.codes.OK
    assert backend.prompts == ["first question", "second question"]
    assert ("user", "first question") in backend.histories[1]


async def test_conversation_history_survives_app_restart(tmp_path: Path) -> None:
    """SQLite-backed chat history survives rebuilding the ASGI app."""
    db_path = tmp_path / "conversations.sqlite"

    first_backend = FakeBackend(response="First A2A response")
    async with _client(first_backend, conversation_db_path=db_path) as client:
        first_response = await client.post(
            "/a2a",
            headers=A2A_V1_HEADERS,
            json=_send_message_request("first question"),
        )
        first_task = first_response.json()["result"]["task"]

    second_backend = FakeBackend(response="Second A2A response")
    async with _client(second_backend, conversation_db_path=db_path) as client:
        second_response = await client.post(
            "/a2a",
            headers=A2A_V1_HEADERS,
            json=_send_message_request(
                "second question",
                context_id=first_task["contextId"],
                message_id="message-2",
            ),
        )

    assert second_response.status_code == httpx.codes.OK
    assert second_backend.prompts == ["second question"]
    assert ("user", "first question") in second_backend.histories[0]
    assert ("assistant", "First A2A response") in second_backend.histories[0]


async def test_send_message_uses_runtime_context_file(tmp_path: Path) -> None:
    """Runtime command and AGENTS.md content are passed to the backend."""
    context_file = tmp_path / "AGENTS.md"
    context_file.write_text(
        "# Runtime Agent\nAnswer in Korean with concise context.",
        encoding="utf-8",
    )
    settings = Settings(
        agent_base_url="https://agent.example.com",
        agent_context_file=str(context_file),
        agent_context_command="Follow this A2A server runtime context.",
    )
    backend = FakeBackend(response="Context-aware response")

    async with _client(backend, settings=settings) as client:
        response = await client.post(
            "/a2a",
            headers=A2A_V1_HEADERS,
            json=_send_message_request("hello with context"),
        )

    assert response.status_code == httpx.codes.OK
    assert backend.prompts == ["hello with context"]
    assert backend.instructions == [
        "Runtime command:\n"
        "Follow this A2A server runtime context.\n\n"
        "Context file (AGENTS.md):\n"
        "# Runtime Agent\n"
        "Answer in Korean with concise context.",
    ]


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


def _send_message_request(
    text: str,
    *,
    context_id: str | None = None,
    message_id: str = "message-1",
    reference_task_ids: list[str] | None = None,
    task_id: str | None = None,
) -> dict[str, object]:
    message: dict[str, object] = {
        "messageId": message_id,
        "role": "ROLE_USER",
        "parts": [{"text": text}],
    }
    if context_id is not None:
        message["contextId"] = context_id
    if task_id is not None:
        message["taskId"] = task_id
    if reference_task_ids is not None:
        message["referenceTaskIds"] = reference_task_ids

    return {
        "jsonrpc": "2.0",
        "id": "request-1",
        "method": "SendMessage",
        "params": {
            "message": message,
            "configuration": {"acceptedOutputModes": ["text/plain"]},
        },
    }


def _send_streaming_message_request(text: str) -> dict[str, object]:
    request = _send_message_request(text)
    request["method"] = "SendStreamingMessage"
    return request
