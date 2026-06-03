# Copyright (c) 2026 Danny Kim
"""Read-only workspace browsing for the A2A agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from agent_over_protocol.documents import (
    DocumentReader,
    DocumentReadError,
    JsonObject,
    JsonValue,
    is_supported_document,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


class WorkspaceError(RuntimeError):
    """Raised when workspace access is invalid or unavailable."""


@dataclass(frozen=True)
class Workspace:
    """Read-only file workspace rooted at a single directory."""

    root: Path
    max_read_chars: int
    max_list_entries: int
    max_search_results: int
    max_search_file_bytes: int
    document_reader: DocumentReader

    async def list_directory(self, path: str = ".") -> JsonObject:
        """List files in a workspace directory."""
        return await asyncio.to_thread(self._list_directory_sync, path)

    async def read_file(self, path: str, *, max_chars: int | None = None) -> JsonObject:
        """Read a supported file from the workspace."""
        file_path = await asyncio.to_thread(self._resolve_file_sync, path)
        read_chars = max_chars if max_chars is not None else self.max_read_chars
        try:
            document = await self.document_reader.read(file_path, max_chars=read_chars)
        except DocumentReadError as exc:
            raise WorkspaceError(str(exc)) from exc
        return {
            "kind": "file",
            "path": _display_path(self.root, file_path),
            "document": document,
        }

    async def search_files(self, query: str, path: str = ".") -> JsonObject:
        """Search supported files under a workspace path."""
        normalized_query = query.strip()
        if not normalized_query:
            message = "Search query cannot be empty."
            raise WorkspaceError(message)

        start = await asyncio.to_thread(self._resolve_existing, path)
        candidates = await asyncio.to_thread(self._search_candidates_sync, start)
        results: list[JsonValue] = []
        truncated = False

        for file_path in candidates:
            if len(results) >= self.max_search_results:
                truncated = True
                break
            try:
                text = await self.document_reader.extract_text(
                    file_path,
                    max_chars=self.max_read_chars,
                )
            except DocumentReadError:
                continue
            snippet = _first_match_snippet(text, normalized_query)
            if snippet is not None:
                results.append(
                    {
                        "path": _display_path(self.root, file_path),
                        "snippet": snippet,
                    }
                )

        return {
            "kind": "search_results",
            "query": normalized_query,
            "path": _display_path(self.root, start),
            "results": results,
            "truncated": truncated,
        }

    def _list_directory_sync(self, path: str) -> JsonObject:
        directory = self._resolve_existing(path)
        if not directory.is_dir():
            message = f"Not a directory: {_display_path(self.root, directory)}"
            raise WorkspaceError(message)

        entries = sorted(
            directory.iterdir(),
            key=lambda item: (not item.is_dir(), item.name.lower()),
        )
        visible_entries: list[JsonValue] = [
            _format_entry(self.root, entry)
            for entry in entries[: self.max_list_entries]
            if _is_inside(self.root, entry)
        ]
        return {
            "kind": "directory",
            "path": _display_path(self.root, directory),
            "entries": visible_entries,
            "truncated": len(entries) > self.max_list_entries,
        }

    def _resolve_file_sync(self, path: str) -> Path:
        file_path = self._resolve_existing(path)
        if not file_path.is_file():
            message = f"Not a file: {_display_path(self.root, file_path)}"
            raise WorkspaceError(message)
        return file_path

    def _search_candidates_sync(self, start: Path) -> list[Path]:
        return [
            file_path
            for file_path in _walk_files(start)
            if _is_searchable(self.root, file_path)
            and _is_within_size_limit(file_path, self.max_search_file_bytes)
        ]

    def _resolve_existing(self, path: str) -> Path:
        try:
            root = self.root.resolve(strict=True)
        except FileNotFoundError as exc:
            message = f"Workspace root does not exist: {self.root}"
            raise WorkspaceError(message) from exc
        relative = _relative_path(path)
        candidate = root / relative
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            message = f"Workspace path does not exist: {path or '.'}"
            raise WorkspaceError(message) from exc
        if not _is_inside(root, resolved):
            message = "Workspace path escapes the configured root."
            raise WorkspaceError(message)
        return resolved


def _relative_path(path: str) -> Path:
    normalized = (path or ".").strip().replace("\\", "/")
    if normalized in {"", ".", "/"}:
        return Path()
    pure = PurePosixPath(normalized)
    parts = pure.parts[1:] if pure.is_absolute() else pure.parts
    if any(part in {"..", ""} for part in parts):
        message = "Parent directory traversal is not allowed."
        raise WorkspaceError(message)
    if parts and ":" in parts[0]:
        message = "Drive-qualified paths are not allowed."
        raise WorkspaceError(message)
    return Path(*parts)


def _is_inside(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
    except FileNotFoundError, ValueError:
        return False
    return True


def _format_entry(root: Path, path: Path) -> JsonObject:
    try:
        size: int | None = None if path.is_dir() else path.stat().st_size
    except OSError:
        size = None
    return {
        "kind": "directory" if path.is_dir() else "file",
        "name": path.name,
        "path": _display_path(root, path),
        "size_bytes": size,
    }


def _display_path(root: Path, path: Path) -> str:
    try:
        relative = path.resolve(strict=False).relative_to(root.resolve(strict=True))
    except FileNotFoundError, ValueError:
        return "."
    rendered = relative.as_posix()
    return rendered or "."


def _walk_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    yield from (
        child
        for child in sorted(path.rglob("*"), key=lambda item: item.as_posix().lower())
        if child.is_file()
    )


def _first_match_snippet(content: str, query: str) -> str | None:
    folded_query = query.casefold()
    for line in content.splitlines():
        if folded_query in line.casefold():
            return line.strip()[:500]
    return None


def _is_searchable(root: Path, path: Path) -> bool:
    return _is_inside(root, path) and is_supported_document(path)


def _is_within_size_limit(path: Path, max_bytes: int) -> bool:
    try:
        return path.stat().st_size <= max_bytes
    except OSError:
        return False
