# Copyright (c) 2026 Danny Kim
"""A2A agent executor implementation."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

from a2a.helpers.proto_helpers import get_message_text
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils.errors import InvalidParamsError

from agent_over_protocol.context import ContextLoadError
from agent_over_protocol.llm import ChatMessage, ChatRole, ModelBackendError

MAX_STORED_CHAT_MESSAGES = 40
CONVERSATION_METADATA_KEYS = frozenset(
    {
        "channelid",
        "chatid",
        "conversationid",
        "roomid",
        "sessionid",
        "threadid",
        "userid",
        "workspaceid",
    }
)
CONVERSATION_HEADER_KEYS = frozenset(
    {
        "x-channel-id",
        "x-chat-id",
        "x-conversation-id",
        "x-room-id",
        "x-session-id",
        "x-thread-id",
        "x-user-id",
        "x-workspace-id",
    }
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from a2a.server.events.event_queue_v2 import EventQueue

    from agent_over_protocol.context import InstructionProvider
    from agent_over_protocol.conversation import ConversationStore
    from agent_over_protocol.llm import ChatBackend
    from agent_over_protocol.tools import AgentTool


class OpenRouterAgentExecutor(AgentExecutor):
    """A2A executor that answers text prompts with an async chat backend."""

    def __init__(
        self,
        backend: ChatBackend,
        *,
        conversation_store: ConversationStore,
        instruction_provider: InstructionProvider | None = None,
        tools: Sequence[AgentTool] = (),
    ) -> None:
        """Initialize the executor."""
        self._backend = backend
        self._instruction_provider = instruction_provider
        self._conversation_store = conversation_store
        self._tools = tools

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute a user request and publish A2A task events."""
        task_id = _require_id(context.task_id, "task_id")
        context_id = _require_id(context.context_id, "context_id")

        await event_queue.enqueue_event(_initial_task(context, task_id, context_id))

        prompt = context.get_user_input().strip()
        if not prompt:
            message = _agent_message(
                task_id,
                context_id,
                "Please send a text prompt for the agent to answer.",
            )
            await event_queue.enqueue_event(
                _status_event(
                    task_id,
                    context_id,
                    TaskState.TASK_STATE_REJECTED,
                    message,
                )
            )
            return

        await event_queue.enqueue_event(
            _status_event(task_id, context_id, TaskState.TASK_STATE_WORKING)
        )

        try:
            instructions = await self._load_instructions()
            history = await self._history_for(task_id, context_id, context)
            answer = await self._backend.complete(
                prompt,
                instructions=instructions,
                history=history,
                tools=self._tools,
            )
        except (ContextLoadError, ModelBackendError) as exc:
            message = _agent_message(task_id, context_id, str(exc))
            await event_queue.enqueue_event(
                _artifact_event(task_id, context_id, str(exc), name="error")
            )
            await event_queue.enqueue_event(
                _status_event(
                    task_id,
                    context_id,
                    TaskState.TASK_STATE_FAILED,
                    message,
                )
            )
            return

        await self._remember_exchange(task_id, context_id, context, prompt, answer)

        message = _agent_message(task_id, context_id, answer)
        await event_queue.enqueue_event(
            _artifact_event(task_id, context_id, answer, name="response")
        )
        await event_queue.enqueue_event(
            _status_event(
                task_id,
                context_id,
                TaskState.TASK_STATE_COMPLETED,
                message,
            )
        )

    async def _load_instructions(self) -> str | None:
        if self._instruction_provider is None:
            return None
        return await self._instruction_provider.load()

    async def _history_for(
        self,
        task_id: str,
        context_id: str,
        context: RequestContext,
    ) -> list[ChatMessage]:
        task_history = _chat_history(context)
        keys = _conversation_keys(task_id, context_id, context)
        stored_history = await self._conversation_store.load(keys)
        return _merge_chat_history(stored_history, task_history)

    async def _remember_exchange(
        self,
        task_id: str,
        context_id: str,
        context: RequestContext,
        prompt: str,
        answer: str,
    ) -> None:
        keys = _conversation_keys(task_id, context_id, context)
        exchange = [
            ChatMessage(role="user", content=prompt),
            ChatMessage(role="assistant", content=answer),
        ]
        await self._conversation_store.append(keys, exchange)

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Publish a cancellation event for the active task."""
        task_id = _require_id(context.task_id, "task_id")
        context_id = _require_id(context.context_id, "context_id")
        await event_queue.enqueue_event(
            _status_event(
                task_id,
                context_id,
                TaskState.TASK_STATE_CANCELED,
                _agent_message(task_id, context_id, "Task canceled."),
            )
        )


def _require_id(value: str | None, label: str) -> str:
    if value:
        return value
    message = f"Missing required {label}"
    raise InvalidParamsError(message=message)


def _initial_task(
    context: RequestContext,
    task_id: str,
    context_id: str,
) -> Task:
    history = [context.message] if context.message is not None else []
    return Task(
        id=task_id,
        context_id=context_id,
        status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
        history=history,
    )


def _chat_history(context: RequestContext) -> list[ChatMessage]:
    current_message_id = context.message.message_id if context.message else ""
    histories: list[list[ChatMessage]] = []

    current_task = context.current_task
    if current_task is not None:
        histories.append(_task_chat_history(current_task, current_message_id))

    histories.extend(
        _task_chat_history(task, current_message_id) for task in context.related_tasks
    )
    return _merge_chat_history(*histories)


def _task_chat_history(task: Task, current_message_id: str) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for message in task.history:
        if message.message_id and message.message_id == current_message_id:
            continue

        role = _chat_role(message.role)
        if role is None:
            continue

        content = get_message_text(message).strip()
        if content:
            messages.append(ChatMessage(role=role, content=content))
    return messages


def _chat_role(role: Role) -> ChatRole | None:
    if role == Role.ROLE_USER:
        return "user"
    if role == Role.ROLE_AGENT:
        return "assistant"
    return None


def _conversation_keys(
    task_id: str,
    context_id: str,
    context: RequestContext,
) -> list[str]:
    keys: list[str] = []
    _append_key(keys, "context", context_id)
    _append_key(keys, "task", task_id)

    for reference_task_id in _reference_task_ids(context):
        _append_key(keys, "task", reference_task_id)
    for task in context.related_tasks:
        _append_key(keys, "task", task.id)
        _append_key(keys, "context", task.context_id)

    for key, value in context.metadata.items():
        normalized = _normalized_key(key)
        if normalized in CONVERSATION_METADATA_KEYS:
            _append_key(keys, f"metadata:{normalized}", value)

    for key, value in _request_headers(context).items():
        normalized = key.lower()
        if normalized in CONVERSATION_HEADER_KEYS:
            _append_key(keys, f"header:{normalized}", value)

    _append_key(keys, "scope", _fallback_scope(context))
    return keys


def _reference_task_ids(context: RequestContext) -> list[str]:
    message = context.message
    if message is None:
        return []

    reference_task_ids = cast(
        "Sequence[str]",
        getattr(message, "reference_task_ids", ()),
    )
    return [task_id for task_id in reference_task_ids if task_id]


def _request_headers(context: RequestContext) -> dict[str, str]:
    headers = context.call_context.state.get("headers", {})
    if not isinstance(headers, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in headers.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _fallback_scope(context: RequestContext) -> str:
    user_name = getattr(context.call_context.user, "user_name", "")
    if isinstance(user_name, str) and user_name:
        return f"user:{user_name}"

    if context.tenant:
        return f"tenant:{context.tenant}"

    headers = _request_headers(context)
    forwarded_for = headers.get("x-forwarded-for", "")
    if forwarded_for:
        return f"client:{forwarded_for.split(',', maxsplit=1)[0].strip()}"

    real_ip = headers.get("x-real-ip", "")
    if real_ip:
        return f"client:{real_ip}"

    return "process:default"


def _append_key(keys: list[str], namespace: str, value: object) -> None:
    if isinstance(value, bool) or value is None:
        return
    if not isinstance(value, str | int):
        return
    stripped = str(value).strip()
    if not stripped:
        return

    key = f"{namespace}:{stripped}"
    if key not in keys:
        keys.append(key)


def _normalized_key(key: str) -> str:
    return key.lower().replace("-", "").replace("_", "")


def _merge_chat_history(
    *histories: Sequence[ChatMessage],
) -> list[ChatMessage]:
    merged: list[ChatMessage] = []
    seen: set[tuple[ChatRole, str]] = set()
    for history in histories:
        for message in history:
            key = (message.role, message.content)
            if key in seen:
                continue
            seen.add(key)
            merged.append(message)
    return merged


def _status_event(
    task_id: str,
    context_id: str,
    state: TaskState,
    message: Message | None = None,
) -> TaskStatusUpdateEvent:
    return TaskStatusUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        status=TaskStatus(state=state, message=message),
    )


def _artifact_event(
    task_id: str,
    context_id: str,
    text: str,
    *,
    name: str,
) -> TaskArtifactUpdateEvent:
    return TaskArtifactUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        artifact=Artifact(
            artifact_id=str(uuid.uuid4()),
            name=name,
            parts=[Part(text=text)],
        ),
        last_chunk=True,
    )


def _agent_message(task_id: str, context_id: str, text: str) -> Message:
    return Message(
        message_id=str(uuid.uuid4()),
        context_id=context_id,
        task_id=task_id,
        role=Role.ROLE_AGENT,
        parts=[Part(text=text)],
    )
