# Copyright (c) 2026 Danny Kim
"""Regression tests for persistent tool evidence and existing databases."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

from agent_over_protocol.conversation import SQLiteConversationStore
from agent_over_protocol.executor import _merge_chat_history
from agent_over_protocol.llm import ChatMessage, ToolExchange, ToolResult

if TYPE_CHECKING:
    from pathlib import Path


def _answer(call_id: str) -> ChatMessage:
    return ChatMessage(
        role="assistant",
        content="Done.",
        tool_exchanges=(
            ToolExchange(
                content=None,
                results=(
                    ToolResult(
                        call_id=call_id,
                        name="read_file",
                        arguments='{"path": "note.txt"}',
                        result='{"text": "file evidence"}',
                    ),
                ),
            ),
        ),
    )


async def test_repeated_answers_keep_distinct_tool_evidence(tmp_path: Path) -> None:
    """Identical final text cannot erase evidence from separate tool turns."""
    store = SQLiteConversationStore(tmp_path / "chat.sqlite", max_messages=40)
    await store.append(["context"], [_answer("first"), _answer("second")])

    messages = _merge_chat_history(
        await store.load(["context"]),
        [ChatMessage(role="assistant", content="Done.")],
    )

    assert [
        result.call_id
        for message in messages
        for exchange in message.tool_exchanges
        for result in exchange.results
    ] == ["first", "second"]
    assert messages == [_answer("first"), _answer("second")]


async def test_legacy_database_keeps_existing_history(tmp_path: Path) -> None:
    """Adding tool evidence preserves pre-migration rows and context aliases."""
    path = tmp_path / "legacy.sqlite"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript(
            "CREATE TABLE conversation_aliases (alias TEXT PRIMARY KEY, "
            "conversation_id TEXT NOT NULL, updated_at TEXT "
            "NOT NULL DEFAULT CURRENT_TIMESTAMP);"
            "CREATE TABLE conversation_messages (id INTEGER PRIMARY KEY "
            "AUTOINCREMENT, conversation_id TEXT NOT NULL, role TEXT NOT NULL "
            "CHECK(role IN ('user', 'assistant')), content TEXT NOT NULL, "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);"
            "INSERT INTO conversation_aliases(alias, conversation_id) "
            "VALUES ('context', 'legacy');"
            "INSERT INTO conversation_messages(conversation_id, role, content) "
            "VALUES ('legacy', 'user', 'Old question');"
        )

    store = SQLiteConversationStore(path, max_messages=40)
    await store.append(["context", "task"], [_answer("new-call")])
    restarted = SQLiteConversationStore(path, max_messages=40)

    assert await restarted.load(["task"]) == [
        ChatMessage(role="user", content="Old question"),
        _answer("new-call"),
    ]


async def test_pruning_removes_expired_tool_evidence(tmp_path: Path) -> None:
    """History limits remove old tool payloads along with their parent reply."""
    path = tmp_path / "chat.sqlite"
    store = SQLiteConversationStore(path, max_messages=1)
    await store.append(["context"], [_answer("expired")])
    await store.append(["context"], [_answer("retained")])

    assert await store.load(["context"]) == [_answer("retained")]
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            "SELECT exchanges FROM conversation_tool_exchanges",
        ).fetchall()
    assert len(rows) == 1
    assert "expired" not in rows[0][0]
    assert "retained" in rows[0][0]
