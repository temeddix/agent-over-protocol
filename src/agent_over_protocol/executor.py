# Copyright (c) 2026 Danny Kim
"""A2A agent executor implementation."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

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
from agent_over_protocol.llm import ModelBackendError

if TYPE_CHECKING:
    from a2a.server.events.event_queue_v2 import EventQueue

    from agent_over_protocol.context import InstructionProvider
    from agent_over_protocol.llm import ChatBackend


class OpenRouterAgentExecutor(AgentExecutor):
    """A2A executor that answers text prompts with an async chat backend."""

    def __init__(
        self,
        backend: ChatBackend,
        *,
        instruction_provider: InstructionProvider | None = None,
    ) -> None:
        """Initialize the executor."""
        self._backend = backend
        self._instruction_provider = instruction_provider

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
            answer = await self._backend.complete(prompt, instructions=instructions)
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
