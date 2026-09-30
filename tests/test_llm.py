# Copyright (c) 2026 Danny Kim
"""Tests for the OpenAI-compatible model backend's HTTP contract."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest

from agent_over_protocol.llm import (
    ChatMessage,
    ModelBackendError,
    OpenAICompatibleBackend,
)
from agent_over_protocol.server import create_app
from agent_over_protocol.settings import Settings
from agent_over_protocol.tools import build_workspace_tools

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_httpx import HTTPXMock


@pytest.fixture(autouse=True)
def ignore_local_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ignored local dotenv credentials out of provider tests."""
    monkeypatch.setattr(
        Settings, "model_config", {**Settings.model_config, "env_file": None}
    )


@pytest.fixture
def provider_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Load isolated provider configuration from the environment."""
    for name in (
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
        "LLM_BASE_URL",
        "LLM_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "test-brain-key")
    return Settings()


async def test_brain_completion_preserves_context(
    provider_settings: Settings,
    httpx_mock: HTTPXMock,
) -> None:
    """Requests use Brain credentials and toddler while preserving chat context."""
    httpx_mock.add_response(
        url="https://brain.temeddix.me/v1/chat/completions",
        method="POST",
        json=_completion({"role": "assistant", "content": "Hello."}),
    )
    backend = OpenAICompatibleBackend.from_settings(provider_settings)

    answer = await backend.complete(
        "hello",
        instructions="Be concise.",
        history=[ChatMessage(role="user", content="Previous question")],
    )

    assert answer.content == "Hello."
    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Authorization"] == "Bearer test-brain-key"
    assert json.loads(request.content) == {
        "model": "toddler",
        "messages": [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Previous question"},
            {"role": "user", "content": "hello"},
        ],
    }


async def test_provider_environment_overrides_reach_the_api(
    provider_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    httpx_mock: HTTPXMock,
) -> None:
    """Changing provider environment values changes the outgoing request."""
    del provider_settings
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.test/custom/v1")
    monkeypatch.setenv("LLM_MODEL", "custom-model")
    httpx_mock.add_response(
        url="https://provider.test/custom/v1/chat/completions",
        method="POST",
        json=_completion({"role": "assistant", "content": "Custom reply."}),
    )
    backend = OpenAICompatibleBackend.from_settings(Settings())

    assert (await backend.complete("hello")).content == "Custom reply."
    request = httpx_mock.get_request()
    assert request is not None
    assert json.loads(request.content)["model"] == "custom-model"


async def test_brain_tool_call_returns_result_to_model(
    provider_settings: Settings,
    httpx_mock: HTTPXMock,
    tmp_path: Path,
) -> None:
    """Function calls execute and their results reach the next Brain request."""
    (tmp_path / "note.txt").write_text("A note from the workspace.", encoding="utf-8")
    provider_settings.agent_workspace_root = str(tmp_path)
    httpx_mock.add_response(
        json=_completion(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path": "note.txt"}',
                        },
                    },
                ],
            },
        ),
    )
    httpx_mock.add_response(
        json=_completion({"role": "assistant", "content": "I read the note."}),
    )
    backend = OpenAICompatibleBackend.from_settings(provider_settings)

    answer = await backend.complete(
        "Use a tool.",
        tools=build_workspace_tools(provider_settings),
    )

    assert answer.content == "I read the note."
    first_request, followup_request = httpx_mock.get_requests()
    assert str(first_request.url) == "https://brain.temeddix.me/v1/chat/completions"
    payload = json.loads(followup_request.content)
    assert payload["model"] == "toddler"
    assert payload["tool_choice"] == "auto"
    assert payload["messages"][-1]["role"] == "tool"
    assert payload["messages"][-1]["tool_call_id"] == "call-1"
    result = json.loads(payload["messages"][-1]["content"])
    assert result["document"]["text"] == "A note from the workspace."


@pytest.mark.parametrize("with_tools", [False, True])
@pytest.mark.parametrize(
    ("status_code", "body"),
    [
        (401, {"error": {"message": "private provider details"}}),
        (200, {"choices": []}),
        (200, {"choices": [{"message": {"role": "assistant", "content": " "}}]}),
    ],
)
async def test_unusable_provider_response_is_sanitized(
    provider_settings: Settings,
    httpx_mock: HTTPXMock,
    status_code: int,
    body: dict[str, object],
    *,
    with_tools: bool,
) -> None:
    """Provider failures become safe errors in ordinary and tool-enabled chat."""
    httpx_mock.add_response(status_code=status_code, json=body)
    backend = OpenAICompatibleBackend.from_settings(provider_settings)
    tools = build_workspace_tools(provider_settings) if with_tools else []

    with pytest.raises(ModelBackendError) as exc_info:
        await backend.complete("hello", tools=tools)

    assert "private provider details" not in str(exc_info.value)
    assert "test-brain-key" not in str(exc_info.value)


def test_missing_brain_key_does_not_reuse_openrouter_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An old provider's credentials cannot silently get sent to Brain."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "old-provider-key")

    with pytest.raises(ModelBackendError, match="LLM_API_KEY is required"):
        OpenAICompatibleBackend.from_settings(Settings())


async def test_a2a_tool_evidence_survives_restart(
    provider_settings: Settings,
    httpx_mock: HTTPXMock,
    tmp_path: Path,
) -> None:
    """Later Brain requests retain tool evidence without exposing it over A2A."""
    (tmp_path / "note.txt").write_text("Verified marker: COBALT-814.")
    provider_settings.agent_workspace_root = str(tmp_path)
    provider_settings.agent_context_file = None
    provider_settings.agent_conversation_db_path = str(tmp_path / "chat.sqlite")
    httpx_mock.add_response(
        json=_completion(
            {
                "role": "assistant",
                "content": "Checking the file.",
                "tool_calls": [
                    {
                        "id": "read-note",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path": "note.txt"}',
                        },
                    },
                    {
                        "id": "missing-note",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path": "missing.txt"}',
                        },
                    },
                ],
            },
        ),
    )
    for _ in range(2):
        httpx_mock.add_response(
            json=_completion({"role": "assistant", "content": "COBALT-814"}),
        )

    for index, prompt in enumerate(("Read note.txt.", "What did you read?")):
        app = create_app(settings=provider_settings)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/a2a",
                headers={"A2A-Version": "1.0"},
                json={
                    "jsonrpc": "2.0",
                    "id": index,
                    "method": "SendMessage",
                    "params": {
                        "message": {
                            "messageId": f"message-{index}",
                            "contextId": "tool-history-test",
                            "role": "ROLE_USER",
                            "parts": [{"text": prompt}],
                        },
                    },
                },
            )
        task = response.json()["result"]["task"]
        assert task["status"]["state"] == "TASK_STATE_COMPLETED"
        assert task["artifacts"][0]["parts"] == [{"text": "COBALT-814"}]
        assert "Verified marker" not in response.text
        assert "missing-note" not in response.text

    messages = json.loads(httpx_mock.get_requests()[-1].content)["messages"]
    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "tool",
        "assistant",
        "user",
    ]
    assert messages[2]["content"] == "Checking the file."
    assert messages[2]["tool_calls"][0]["function"]["arguments"] == (
        '{"path": "note.txt"}'
    )
    assert messages[3]["tool_call_id"] == "read-note"
    assert json.loads(messages[3]["content"])["document"]["text"] == (
        "Verified marker: COBALT-814."
    )
    assert messages[4]["tool_call_id"] == "missing-note"
    assert json.loads(messages[4]["content"])["kind"] == "error"
    assert messages[-2] == {"role": "assistant", "content": "COBALT-814"}


def _completion(message: dict[str, object]) -> dict[str, object]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "toddler",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
    }
