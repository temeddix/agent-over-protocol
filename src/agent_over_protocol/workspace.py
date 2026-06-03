# Copyright (c) 2026 Danny Kim
"""Read-only workspace browsing for the A2A agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from agent_over_protocol.documents import (
    DocumentReadError,
    is_supported_document,
    read_document,
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

    async def list_directory(self, path: str = ".") -> str:
        """List files in a workspace directory."""
        return await asyncio.to_thread(self._list_directory_sync, path)

    async def read_file(self, path: str, *, max_chars: int | None = None) -> str:
        """Read a supported file from the workspace."""
        return await asyncio.to_thread(self._read_file_sync, path, max_chars)

    async def search_files(self, query: str, path: str = ".") -> str:
        """Search supported files under a workspace path."""
        return await asyncio.to_thread(self._search_files_sync, query, path)

    def _list_directory_sync(self, path: str) -> str:
        directory = self._resolve_existing(path)
        if not directory.is_dir():
            message = f"Not a directory: {_display_path(self.root, directory)}"
            raise WorkspaceError(message)

        entries = sorted(
            directory.iterdir(),
            key=lambda item: (not item.is_dir(), item.name.lower()),
        )
        lines = [f"Directory: {_display_path(self.root, directory)}"]
        for entry in entries[: self.max_list_entries]:
            if not _is_inside(self.root, entry):
                continue
            lines.append(_format_entry(entry))
        if len(entries) > self.max_list_entries:
            lines.append(f"[Truncated after {self.max_list_entries} entries.]")
        return "\n".join(lines)

    def _read_file_sync(self, path: str, max_chars: int | None) -> str:
        file_path = self._resolve_existing(path)
        if not file_path.is_file():
            message = f"Not a file: {_display_path(self.root, file_path)}"
            raise WorkspaceError(message)
        read_chars = max_chars if max_chars is not None else self.max_read_chars
        try:
            content = read_document(file_path, max_chars=read_chars)
        except DocumentReadError as exc:
            raise WorkspaceError(str(exc)) from exc
        return f"Path: {_display_path(self.root, file_path)}\n\n{content}"

    def _search_files_sync(self, query: str, path: str) -> str:
        normalized_query = query.strip()
        if not normalized_query:
            message = "Search query cannot be empty."
            raise WorkspaceError(message)
        start = self._resolve_existing(path)
        candidates = _walk_files(start) if start.is_dir() else [start]
        results: list[str] = []
        for file_path in candidates:
            if len(results) >= self.max_search_results:
                break
            if not _is_searchable(self.root, file_path):
                continue
            try:
                if file_path.stat().st_size > self.max_search_file_bytes:
                    continue
                content = read_document(file_path, max_chars=self.max_read_chars)
            except DocumentReadError, OSError:
                continue
            snippet = _first_match_snippet(content, normalized_query)
            if snippet is not None:
                results.append(f"{_display_path(self.root, file_path)}: {snippet}")
        if not results:
            display_path = _display_path(self.root, start)
            return f"No matches for {normalized_query!r} under {display_path}."
        return "\n".join(results)

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


def _format_entry(path: Path) -> str:
    kind = "DIR" if path.is_dir() else "FILE"
    suffix = "/" if path.is_dir() else ""
    try:
        size = "" if path.is_dir() else f" {path.stat().st_size} bytes"
    except OSError:
        size = ""
    return f"[{kind}] {path.name}{suffix}{size}"


def _display_path(root: Path, path: Path) -> str:
    try:
        relative = path.resolve(strict=False).relative_to(root.resolve(strict=True))
    except FileNotFoundError, ValueError:
        return "."
    rendered = relative.as_posix()
    return rendered or "."


def _walk_files(path: Path) -> Iterable[Path]:
    for child in sorted(path.rglob("*"), key=lambda item: item.as_posix().lower()):
        if child.is_file():
            yield child


def _first_match_snippet(content: str, query: str) -> str | None:
    folded_query = query.casefold()
    for line in content.splitlines():
        if folded_query in line.casefold():
            return line.strip()[:500]
    return None


def _is_searchable(root: Path, path: Path) -> bool:
    return _is_inside(root, path) and is_supported_document(path)
