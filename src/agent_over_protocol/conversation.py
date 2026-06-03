# Copyright (c) 2026 Danny Kim
# ruff: noqa: S608
"""Persistent chat history storage for A2A conversations."""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from agent_over_protocol.llm import ChatMessage, ChatRole

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


class ConversationStore(Protocol):
    """Async storage boundary for model-facing conversation history."""

    async def load(self, keys: Sequence[str]) -> list[ChatMessage]:
        """Load merged chat history for any matching conversation key."""

    async def append(
        self,
        keys: Sequence[str],
        messages: Sequence[ChatMessage],
    ) -> None:
        """Append messages and associate all keys with the same conversation."""


class SQLiteConversationStore:
    """SQLite-backed conversation store using worker threads for blocking I/O."""

    def __init__(self, path: str | Path, *, max_messages: int) -> None:
        """Create a store rooted at the given SQLite database path."""
        self._path = Path(path)
        self._max_messages = max_messages
        self._lock = asyncio.Lock()

    async def load(self, keys: Sequence[str]) -> list[ChatMessage]:
        """Load merged chat history for any matching conversation key."""
        normalized_keys = _normalized_keys(keys)
        if not normalized_keys:
            return []

        async with self._lock:
            return await asyncio.to_thread(self._load_sync, normalized_keys)

    async def append(
        self,
        keys: Sequence[str],
        messages: Sequence[ChatMessage],
    ) -> None:
        """Append messages and associate all keys with the same conversation."""
        normalized_keys = _normalized_keys(keys)
        normalized_messages = [
            message for message in messages if message.content.strip()
        ]
        if not normalized_keys or not normalized_messages:
            return

        async with self._lock:
            await asyncio.to_thread(
                self._append_sync,
                normalized_keys,
                normalized_messages,
            )

    def _load_sync(self, keys: Sequence[str]) -> list[ChatMessage]:
        with closing(self._connect()) as connection:
            conversation_ids = _conversation_ids(connection, keys)
            if not conversation_ids:
                return []

            placeholders = ",".join("?" for _ in conversation_ids)
            rows = connection.execute(
                "SELECT role, content FROM conversation_messages "
                f"WHERE conversation_id IN ({placeholders}) "
                "ORDER BY id",
                tuple(conversation_ids),
            ).fetchall()

        return _dedupe_messages(
            ChatMessage(role=cast("ChatRole", role), content=content)
            for role, content in rows
        )[-self._max_messages :]

    def _append_sync(
        self,
        keys: Sequence[str],
        messages: Sequence[ChatMessage],
    ) -> None:
        with closing(self._connect()) as connection, connection:
            conversation_ids = _conversation_ids(connection, keys)
            conversation_id = conversation_ids[0] if conversation_ids else keys[0]

            for alias in keys:
                connection.execute(
                    "INSERT INTO conversation_aliases(alias, conversation_id) "
                    "VALUES (?, ?) "
                    "ON CONFLICT(alias) DO UPDATE SET "
                    "conversation_id = excluded.conversation_id, "
                    "updated_at = CURRENT_TIMESTAMP",
                    (alias, conversation_id),
                )

            for merged_id in conversation_ids[1:]:
                connection.execute(
                    "UPDATE conversation_messages SET conversation_id = ? "
                    "WHERE conversation_id = ?",
                    (conversation_id, merged_id),
                )
                connection.execute(
                    "UPDATE conversation_aliases SET conversation_id = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE conversation_id = ?",
                    (conversation_id, merged_id),
                )

            connection.executemany(
                "INSERT INTO conversation_messages(conversation_id, role, content) "
                "VALUES (?, ?, ?)",
                [
                    (conversation_id, message.role, message.content)
                    for message in messages
                ],
            )
            connection.execute(
                "DELETE FROM conversation_messages "
                "WHERE conversation_id = ? "
                "AND id NOT IN ("
                "SELECT id FROM conversation_messages "
                "WHERE conversation_id = ? ORDER BY id DESC LIMIT ?"
                ")",
                (conversation_id, conversation_id, self._max_messages),
            )

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        _ensure_schema(connection)
        return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS conversation_aliases ("
        "alias TEXT PRIMARY KEY, "
        "conversation_id TEXT NOT NULL, "
        "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
        ")"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS conversation_messages ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "conversation_id TEXT NOT NULL, "
        "role TEXT NOT NULL CHECK(role IN ('user', 'assistant')), "
        "content TEXT NOT NULL, "
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation "
        "ON conversation_messages(conversation_id, id)"
    )


def _conversation_ids(
    connection: sqlite3.Connection,
    keys: Sequence[str],
) -> list[str]:
    placeholders = ",".join("?" for _ in keys)
    rows = connection.execute(
        "SELECT alias, conversation_id FROM conversation_aliases "
        f"WHERE alias IN ({placeholders})",
        tuple(keys),
    ).fetchall()
    by_alias = dict(rows)

    ordered: list[str] = []
    for key in keys:
        conversation_id = by_alias.get(key)
        if conversation_id and conversation_id not in ordered:
            ordered.append(conversation_id)
    return ordered


def _normalized_keys(keys: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    for key in keys:
        stripped = key.strip()
        if stripped and stripped not in normalized:
            normalized.append(stripped)
    return normalized


def _dedupe_messages(messages: Iterable[ChatMessage]) -> list[ChatMessage]:
    deduped: list[ChatMessage] = []
    seen: set[tuple[ChatRole, str]] = set()
    for message in messages:
        key = (message.role, message.content)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(message)
    return deduped
